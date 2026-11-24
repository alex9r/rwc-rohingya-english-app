"""Recommend confidence thresholds from clips whose word error rate is known.

It answers "where should the high/medium/low lines go?". WER is scored by Luna's
evaluation code (``ml.eval``), never re-implemented here. Three ways in, which can be
combined, so the lines can be re-tuned as more checked clips come in:

    # Luna's report + the manifest it was run on: transcribes each clip once to get its
    # confidence, with the proxy language recorded in the report
    python -m ml.speech.calibrate --report eval_report.json --manifest manifest.jsonl --model small

    # the review queue (review.py): clips the app was unsure about, checked by a Rohingya
    # speaker. Each record already holds its confidence and what the model heard, so no
    # model runs; the reviewer's transcript is the reference for the WER.
    python -m ml.speech.calibrate --queue speech_review --model small

    # or a CSV that already has a 'confidence' and a 'wer' column, one row per clip
    python -m ml.speech.calibrate results_with_wer.csv

    # all together
    python -m ml.speech.calibrate --report r.json --manifest m.jsonl --queue speech_review

Use the same model as the evaluation run; thresholds for one model don't carry over to
another (queue clips saved with a different model are left out). Put the result in
RWC_HIGH_CONFIDENCE / RWC_LOW_CONFIDENCE for that deployment.

Besides the lines, it prints how many clips the app asks to repeat at the current and
at the recommended LOW line, and how many of those it had heard right anyway: the
repeats users didn't need. The review queue only holds clips the app was unsure about,
so these are counts of checked clips, not shares of real traffic.

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


def clips_from_queue(root: Path, model: Optional[str], fold_marks: bool = False) -> tuple[list[Clip], dict[str, int]]:
    """Reviewed clips from the review queue, scored with Luna's ``score_clip``; no model runs.

    Confidence is the one transcribe() gave when the clip was saved. Left out, and
    counted: clips not reviewed yet, rejected clips, clips transcribed by a model other
    than ``model``, and clips with no WER (heard in a different script from the
    reviewer's transcript, which Luna's evaluation doesn't score either).
    """
    from ..eval.metrics import score_clip
    from .review import ReviewQueue

    if not root.is_dir():
        raise CalibrationError(f"no review queue at {root}")
    clips: list[Clip] = []
    skipped = {"not_reviewed": 0, "rejected": 0, "other_model": 0, "no_wer": 0}
    for r in ReviewQueue(root).items():
        asr = r["asr"]
        if r["status"] == "unvalidated":
            skipped["not_reviewed"] += 1
        elif r["status"] == "rejected":
            skipped["rejected"] += 1
        elif model and asr.get("model") and asr["model"] != model:
            skipped["other_model"] += 1
        else:
            wer = score_clip(r["clip_id"], r["reference"], asr["text"] or "", fold_marks=fold_marks).wer
            if wer is None:
                skipped["no_wer"] += 1
            else:
                clips.append((float(asr["confidence"]), wer))
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


def repeats(clips: list[Clip], low: float, accept_wer: float) -> tuple[int, int]:
    """(clips the app asks to repeat at this LOW line, how many of them it heard right anyway).

    "Heard right" means WER at most ``accept_wer``: the user repeated for nothing.
    """
    asked = [w for c, w in clips if c < low]
    return len(asked), sum(w <= accept_wer for w in asked)


def _left_out(skipped: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in skipped.items() if v)


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
    ap.add_argument("results", type=Path, nargs="*", help="CSV(s) with 'confidence' and 'wer' columns")
    ap.add_argument("--report", type=Path, help="ml.eval report JSON (Luna's evaluation output)")
    ap.add_argument("--manifest", type=Path, help="the manifest that report was run on")
    ap.add_argument("--queue", type=Path, action="append", default=[],
                    help="review queue folder; its reviewed clips are added (repeatable)")
    ap.add_argument("--fold-marks", action="store_true",
                    help="for --queue: ignore ' * - spelling marks (as ml.eval run --fold-marks)")
    ap.add_argument("--model", default=None, help="Whisper model; use the one the evaluation used")
    ap.add_argument("--accept-wer", type=float, default=0.10, help="highest mean WER allowed in the high band")
    ap.add_argument("--repeat-wer", type=float, default=0.50, help="lowest mean WER required in the low band")
    args = ap.parse_args(argv)
    if bool(args.report) != bool(args.manifest):
        ap.error("--report and --manifest go together")
    if not (args.results or args.report or args.queue):
        ap.error("give a results CSV, --report with --manifest, or --queue")

    from .transcribe import DEFAULT_MODEL, LOW_CONFIDENCE

    model = args.model or DEFAULT_MODEL
    clips: list[Clip] = []
    try:
        for path in args.results:
            clips += load_clips(path)
        if args.report:
            report = json.loads(args.report.read_text(encoding="utf-8"))
            if scorer is None:
                scorer = whisper_scorer(model)
            eval_clips, skipped = clips_from_eval(report, args.manifest, scorer)
            clips += eval_clips
            print(f"evaluation report: {len(eval_clips)} clips, proxy language {report.get('asr_language')}")
            if _left_out(skipped):
                print(f"  left out: {_left_out(skipped)}")
        for root in args.queue:
            queue_clips, skipped = clips_from_queue(root, model, args.fold_marks)
            clips += queue_clips
            print(f"review queue {root}: {len(queue_clips)} reviewed clips")
            if _left_out(skipped):
                print(f"  left out: {_left_out(skipped)}")
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

    lines = [("current", LOW_CONFIDENCE)] + ([("recommended", low)] if low is not None else [])
    print(f"\nrepeats (heard right anyway = WER <= {args.accept_wer:.2f}):")
    for name, line in lines:
        asked, needless = repeats(clips, line, args.accept_wer)
        print(f"  {name:<11} LOW {line:.2f}: asks to repeat {asked} clips, {needless} of them heard right anyway")

    if high is not None and low is not None:
        print(f"\nset for this model: RWC_HIGH_CONFIDENCE={high} RWC_LOW_CONFIDENCE={low}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
