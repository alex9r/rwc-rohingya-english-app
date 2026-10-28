"""Run transcribe() over a batch of dataset clips and write a results CSV.

This is the "test on top dataset clips" step: it checks the function holds up on
real recordings (statuses, confidence, speed). Accuracy (WER) is Hari's evaluation,
not this script.

Usage (from the repo root):

    # a folder of clips
    python -m ml.speech.run_clips path/to/clips --language bn --limit 30

    # a manifest CSV/TSV with a path column
    python -m ml.speech.run_clips manifest.tsv --path-col path --out results.csv
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


def load_paths(src: Path, path_col: str) -> list[Path]:
    if src.is_dir():
        return [p for p in sorted(src.rglob("*")) if p.suffix.lower() in AUDIO_EXTS]

    delim = "\t" if src.suffix.lower() in {".tsv", ".tab"} else ","
    with src.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=delim))
    if rows and path_col not in rows[0]:
        sys.exit(f"column {path_col!r} not in manifest; columns are {list(rows[0])}")
    base = src.parent
    return [Path(r[path_col]) if Path(r[path_col]).is_absolute() else base / r[path_col] for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="folder of clips, or a CSV/TSV manifest")
    ap.add_argument("--language", default=None, help="proxy language code (bn, ur, en); omit to auto-detect")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper model size")
    ap.add_argument("--path-col", default="path")
    ap.add_argument("--limit", type=int, default=None, help="only the first N clips")
    ap.add_argument("--out", type=Path, default=Path("transcribe_results.csv"))
    args = ap.parse_args()

    paths = load_paths(args.source, args.path_col)[: args.limit]
    if not paths:
        sys.exit("no clips found")

    fields = ["file", "status", "text", "confidence", "is_confident",
              "language", "duration_s", "processing_s", "error"]
    statuses: Counter[str] = Counter()
    confs, speeds = [], []

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, path in enumerate(paths, 1):
            r = transcribe(path, args.language, model_size=args.model)
            statuses[r.status.value] += 1
            if r.status == Status.OK:
                confs.append(r.confidence)
            if r.duration_s and r.processing_s:
                speeds.append(r.processing_s / r.duration_s)
            w.writerow({
                "file": str(path), "status": r.status.value, "text": r.text,
                "confidence": r.confidence, "is_confident": r.is_confident, "language": r.language,
                "duration_s": r.duration_s, "processing_s": r.processing_s, "error": r.error or "",
            })
            print(f"[{i}/{len(paths)}] {r.status.value:<13} {r.confidence:.2f}  {path.name}  {r.text[:60]}")

    print(f"\n{len(paths)} clips -> {args.out}")
    print("status:", dict(statuses))
    if confs:
        print(f"confidence (ok clips): mean {statistics.mean(confs):.2f}, median {statistics.median(confs):.2f}")
    if speeds:
        print(f"speed: {statistics.mean(speeds):.2f}x real time (processing / audio length)")


if __name__ == "__main__":
    main()
