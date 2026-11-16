"""Recommend confidence thresholds from clips whose word error rate is known.

The WER comes from Luna's transcription evaluation (``python -m ml.eval run``); this
script doesn't compute WER, it answers "where should the high/medium/low lines go?".
Two ways in:

    # Luna's report + the manifest it was run on: transcribes each clip once to get its
    # confidence, with the proxy language recorded in the report
    python -m ml.speech.calibrate --report eval_report.json --manifest manifest.jsonl --model small

    # or a CSV that already has a 'confidence' and a 'wer' column, one row per clip
    python -m ml.speech.calibrate results_with_wer.csv

Use the same model as the evaluation run; thresholds for one model don't carry over to
another. Put the result in RWC_HIGH_CONFIDENCE / RWC_LOW_CONFIDENCE for that deployment.

The rule, with both targets adjustable:

* HIGH is the lowest score where the clips at or above it average at most
  --accept-wer word errors, so text used without checking is rarely wrong.
* LOW is the highest score where the clips just below it (within 0.10) average at least
  --repeat-wer word errors, so users are only asked to repeat when the text really is
  poor. Only the nearby clips count, or very bad ones far below would excuse asking
  people to repeat text that was fine.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Callable, Optional

Clip = tuple[float, float]  # (confidence, wer)
# (audio path, proxy language) -> (status, confidence). Injectable so tests need no model.
Scorer = Callable[[Path, Optional[str]], tuple[str, float]]

GRID = [round(i * 0.05, 2) for i in range(1, 20)]  # 0.05 .. 0.95
WINDOW = 0.10  # how far below a candidate LOW line counts as "just below"
MIN_CLIPS = 5  # a band emptier than this can't support a threshold


class CalibrationError(ValueError):
    pass


def load_clips(path: Path) -> list[Clip]:
    """Read (confidence, wer) pairs from a CSV, skipping clips with no WER (failed statuses)."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if rows and not {"confidence", "wer"} <= set(rows[0]):
        raise CalibrationError(f"need 'confidence' and 'wer' columns; found {list(rows[0])}")
    return [(float(r["confidence"]), float(r["wer"])) for r in rows if (r["wer"] or "").strip()]


def _manifest_audio(manifest: Path) -> dict[str, Path]:
    """clip_id -> audio path, resolved against the manifest's folder (as ml.eval does)."""
    audio: dict[str, Path] = {}
    for n, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise CalibrationError(f"{manifest.name} line {n}: not valid JSON ({e.msg})") from None
        if not row.get("clip_id") or not row.get("audio"):
            raise CalibrationError(f"{manifest.name} line {n}: needs clip_id and audio")
        audio[str(row["clip_id"])] = (manifest.parent / row["audio"]).resolve()
    return audio


def clips_from_eval(report: dict, manifest: Path, scorer: Scorer) -> tuple[list[Clip], dict[str, int]]:
    """Pair each clip's WER from Luna's report with the confidence transcribe() gives it.

    Left out, and counted: clips with no WER (script mismatch), clips that failed in the
    evaluation run (their WER of 1.0 says nothing about confidence), clips missing from
    the manifest, and clips that don't come back ``ok`` now.
    """
    language = report.get("asr_language")
    failed = set(report.get("transcriber_failures", {}))
    audio = _manifest_audio(manifest)
    clips: list[Clip] = []
    skipped = {"no_wer": 0, "failed_in_eval": 0, "not_in_manifest": 0, "not_ok_now": 0}
    for row in report.get("clips", []):
        cid = str(row.get("clip_id"))
        if cid in failed:
            skipped["failed_in_eval"] += 1
        elif row.get("wer") is None:
            skipped["no_wer"] += 1
        elif cid not in audio:
            skipped["not_in_manifest"] += 1
        else:
            status, confidence = scorer(audio[cid], language)
            if status != "ok":
                skipped["not_ok_now"] += 1
            else:
                clips.append((confidence, float(row["wer"])))
    return clips, skipped


def whisper_scorer(model_size: str) -> Scorer:
    from .transcribe import transcribe  # lazy: pulls in the model stack

    def run(path: Path, language: Optional[str]) -> tuple[str, float]:
        r = transcribe(path, language, model_size=model_size)
        return r.status.value, r.confidence

    return run


def recommend(clips: list[Clip], accept_wer: float, repeat_wer: float) -> tuple[Optional[float], Optional[float]]:
    """Return (high, low). Either is None when the data can't support that line."""
    high = low = None
    for t in GRID:
        above = [w for c, w in clips if c >= t]
        if len(above) >= MIN_CLIPS and statistics.mean(above) <= accept_wer:
            high = t
            break
    for t in reversed(GRID):
        just_below = [w for c, w in clips if round(t - WINDOW, 2) <= c < t]
        if len(just_below) >= MIN_CLIPS and statistics.mean(just_below) >= repeat_wer:
            low = t
            break
    if high is not None and low is not None and low > high:
        low = high  # the data has no room for a middle band
    return high, low


def band_table(clips: list[Clip], high: float, low: float) -> list[str]:
    """One line per band: clip count, share of clips and WER."""
    bands = [
        (f"high   (>= {high:.2f})", [w for c, w in clips if c >= high]),
        (f"medium ({low:.2f}-{high:.2f})", [w for c, w in clips if low <= c < high]),
        (f"low    (<  {low:.2f})", [w for c, w in clips if c < low]),
    ]
    lines = []
    for name, wers in bands:
        if wers:
            lines.append(f"  {name}: {len(wers):>4} clips ({len(wers) / len(clips):>4.0%})  "
                         f"mean WER {statistics.mean(wers):.2f}  median {statistics.median(wers):.2f}")
        else:
            lines.append(f"  {name}:    0 clips")
    return lines


def main(argv: Optional[list[str]] = None, scorer: Optional[Scorer] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.speech.calibrate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path, nargs="?", help="CSV with 'confidence' and 'wer' columns")
    ap.add_argument("--report", type=Path, help="ml.eval report JSON (Luna's evaluation output)")
    ap.add_argument("--manifest", type=Path, help="the manifest that report was run on")
    ap.add_argument("--model", default=None, help="Whisper model; use the one the evaluation used")
    ap.add_argument("--accept-wer", type=float, default=0.10, help="highest mean WER allowed in the high band")
    ap.add_argument("--repeat-wer", type=float, default=0.50, help="lowest mean WER required in the low band")
    args = ap.parse_args(argv)

    try:
        if args.report or args.manifest:
            if not (args.report and args.manifest) or args.results:
                ap.error("use --report with --manifest, or a results CSV, not both")
            report = json.loads(args.report.read_text(encoding="utf-8"))
            if scorer is None:
                from .transcribe import DEFAULT_MODEL
                scorer = whisper_scorer(args.model or DEFAULT_MODEL)
            clips, skipped = clips_from_eval(report, args.manifest, scorer)
            print(f"proxy language: {report.get('asr_language')}")
            left_out = ", ".join(f"{k} {v}" for k, v in skipped.items() if v)
            if left_out:
                print(f"left out: {left_out}")
        elif args.results:
            clips = load_clips(args.results)
        else:
            ap.error("give a results CSV, or --report and --manifest")
    except CalibrationError as e:
        print(e, file=sys.stderr)
        return 2

    if not clips:
        print("no clips with both a WER and a confidence", file=sys.stderr)
        return 2

    high, low = recommend(clips, args.accept_wer, args.repeat_wer)
    print(f"{len(clips)} clips with WER")
    print(f"recommended HIGH_CONFIDENCE: {high if high is not None else 'none (target not reachable)'}")
    print(f"recommended LOW_CONFIDENCE:  {low if low is not None else 'none (target not reachable)'}")
    if high is not None and low is not None:
        print("\n".join(band_table(clips, high, low)))
        print(f"\nset for this model: RWC_HIGH_CONFIDENCE={high} RWC_LOW_CONFIDENCE={low}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
