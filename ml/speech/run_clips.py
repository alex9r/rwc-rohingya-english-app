"""Run transcribe() over a batch of dataset clips and write a results CSV.

This is the "test on top dataset clips" step: it checks the function holds up on
real recordings (statuses, confidence, speed). Hari's evaluation owns the proper
WER study; if a reference transcript is given, this also reports WER/CER so the
two can be cross-checked.

Usage (from the repo root):

    # a folder of clips; optional reference text in clip.txt next to clip.wav
    python -m ml.speech.run_clips path/to/clips --language bn --limit 50

    # a manifest CSV/TSV with a path column and an optional transcript column
    python -m ml.speech.run_clips manifest.tsv --path-col path --ref-col sentence

    # compare proxy languages on the same clips
    python -m ml.speech.run_clips clips/ --language bn --out results_bn.csv
    python -m ml.speech.run_clips clips/ --language en --out results_en.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

from .transcribe import DEFAULT_MODEL, Status, transcribe

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".webm", ".aac"}


def load_items(src: Path, path_col: str, ref_col: str) -> list[tuple[Path, str | None]]:
    if src.is_dir():
        items = []
        for p in sorted(src.rglob("*")):
            if p.suffix.lower() in AUDIO_EXTS:
                txt = p.with_suffix(".txt")
                items.append((p, txt.read_text(encoding="utf-8").strip() if txt.exists() else None))
        return items

    delim = "\t" if src.suffix.lower() in {".tsv", ".tab"} else ","
    with src.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=delim))
    if rows and path_col not in rows[0]:
        sys.exit(f"column {path_col!r} not in manifest; columns are {list(rows[0])}")
    base = src.parent
    return [
        ((base / r[path_col]) if not Path(r[path_col]).is_absolute() else Path(r[path_col]),
         (r.get(ref_col) or "").strip() or None)
        for r in rows
    ]


def error_rates(ref: str, hyp: str) -> tuple[float | None, float | None]:
    try:
        import jiwer
    except ImportError:
        return None, None
    if not ref.strip():
        return None, None
    hyp = hyp or ""
    return jiwer.wer(ref, hyp), jiwer.cer(ref, hyp)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="folder of clips, or a CSV/TSV manifest")
    ap.add_argument("--language", default=None, help="proxy language code (bn, ur, en); omit to auto-detect")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper model size")
    ap.add_argument("--path-col", default="path")
    ap.add_argument("--ref-col", default="reference")
    ap.add_argument("--limit", type=int, default=None, help="only the first N clips")
    ap.add_argument("--out", type=Path, default=Path("transcribe_results.csv"))
    args = ap.parse_args()

    items = load_items(args.source, args.path_col, args.ref_col)[: args.limit]
    if not items:
        sys.exit("no clips found")

    fields = ["file", "status", "text", "reference", "confidence", "is_confident",
              "language", "duration_s", "processing_s", "wer", "cer", "error"]
    statuses: Counter[str] = Counter()
    confs, speeds, wers, cers = [], [], [], []

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, (path, ref) in enumerate(items, 1):
            r = transcribe(path, args.language, model_size=args.model)
            # A model crash says nothing about accuracy, so keep it out of WER/CER.
            scorable = ref and r.status != Status.MODEL_ERROR
            wer, cer = error_rates(ref, r.text) if scorable else (None, None)
            statuses[r.status.value] += 1
            if r.status == Status.OK:
                confs.append(r.confidence)
            if r.duration_s and r.processing_s:
                speeds.append(r.processing_s / r.duration_s)
            if wer is not None:
                wers.append(wer)
                cers.append(cer)
            w.writerow({
                "file": str(path), "status": r.status.value, "text": r.text, "reference": ref or "",
                "confidence": r.confidence, "is_confident": r.is_confident, "language": r.language,
                "duration_s": r.duration_s, "processing_s": r.processing_s,
                "wer": "" if wer is None else round(wer, 4), "cer": "" if cer is None else round(cer, 4),
                "error": r.error or "",
            })
            print(f"[{i}/{len(items)}] {r.status.value:<13} {r.confidence:.2f}  {path.name}  {r.text[:60]}")

    print(f"\n{len(items)} clips -> {args.out}")
    print("status:", dict(statuses))
    if confs:
        print(f"confidence (ok clips): mean {statistics.mean(confs):.2f}, median {statistics.median(confs):.2f}")
    if speeds:
        print(f"speed: {statistics.mean(speeds):.2f}x real time (processing / audio length)")
    if wers:
        print(f"WER mean {statistics.mean(wers):.2f}, CER mean {statistics.mean(cers):.2f} over {len(wers)} clips with references")


if __name__ == "__main__":
    main()
