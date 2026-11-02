"""Run the pronunciation scorer over the smoke-test clips listed in the manifest.

This is a smoke test, not an evaluation: it checks the scorer behaves sensibly on real
recordings (right target -> high score, deliberately wrong target -> low score). WER and
threshold calibration are Hari's evaluation.

    python -m ml.pronunciation.fetch_tatoeba_clips --out ml/pronunciation/smoke_clips
    python -m ml.pronunciation.smoke_test ml/pronunciation/smoke_clips --out results.csv

Each clip is transcribed once; the cached transcript is reused for the wrong-target
pairings (the same audio scored against another clip's sentence).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ml.speech.transcribe import DEFAULT_MODEL, transcribe

from .scorer import score_pronunciation

MANIFEST = Path(__file__).with_name("smoke_manifest.csv")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", type=Path, help="folder holding the audio files named in the manifest")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--wrong", type=int, default=6, help="how many clips to also score against a wrong sentence")
    ap.add_argument("--out", type=Path, default=Path("pronunciation_smoke_results.csv"))
    args = ap.parse_args()

    with args.manifest.open(newline="", encoding="utf-8") as f:
        clips = list(csv.DictReader(f))

    cache = {}

    def cached(audio, language):
        if audio not in cache:
            cache[audio] = transcribe(audio, language, model_size=args.model)
        return cache[audio]

    rows = []
    for i, c in enumerate(clips):
        path = args.clips / c["file"]
        pairs = [("correct", c["target_text"])]
        if i < args.wrong:  # same audio, the next clip's sentence
            pairs.append(("wrong_target", clips[(i + 1) % len(clips)]["target_text"]))
        for kind, target in pairs:
            r = score_pronunciation(path, target, transcriber=cached)
            rows.append({
                "clip_id": c["clip_id"], "pairing": kind, "accent_label": c["accent_label"],
                "target": target, "heard": r.transcript, "score": "" if r.score is None else r.score,
                "status": r.status, "confidence": r.confidence, "feedback_code": r.feedback_code,
                "needs_improvement": "; ".join(
                    f"{x['word'] or '+'}->{x['heard'] or '-'}" for x in r.needs_improvement
                ),
            })
            print(f"{c['clip_id']:<22} {kind:<12} {str(r.score):>4} {r.status:<20} "
                  f"target={target!r} heard={r.transcript!r}")

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
