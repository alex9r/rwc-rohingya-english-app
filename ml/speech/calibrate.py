"""Recommend confidence thresholds from clips whose word error rate is known.

Takes a CSV with a ``confidence`` and a ``wer`` column, one row per clip: the output of
``run_clips`` with a WER column added from the transcription evaluation. This script
doesn't compute WER; it answers "where should the high/medium/low lines go?".

    python -m ml.speech.calibrate results_with_wer.csv

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
import statistics
import sys
from pathlib import Path
from typing import Optional

Clip = tuple[float, float]  # (confidence, wer)

GRID = [round(i * 0.05, 2) for i in range(1, 20)]  # 0.05 .. 0.95
WINDOW = 0.10  # how far below a candidate LOW line counts as "just below"
MIN_CLIPS = 5  # a band emptier than this can't support a threshold


def load_clips(path: Path) -> list[Clip]:
    """Read (confidence, wer) pairs, skipping clips with no WER (failed statuses)."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if rows and not {"confidence", "wer"} <= set(rows[0]):
        sys.exit(f"need 'confidence' and 'wer' columns; found {list(rows[0])}")
    return [(float(r["confidence"]), float(r["wer"])) for r in rows if r["wer"].strip()]


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path, help="CSV with 'confidence' and 'wer' columns")
    ap.add_argument("--accept-wer", type=float, default=0.10, help="highest mean WER allowed in the high band")
    ap.add_argument("--repeat-wer", type=float, default=0.50, help="lowest mean WER required in the low band")
    args = ap.parse_args()

    clips = load_clips(args.results)
    if not clips:
        sys.exit("no clips with a WER value")

    high, low = recommend(clips, args.accept_wer, args.repeat_wer)
    print(f"{len(clips)} clips with WER")
    print(f"recommended HIGH_CONFIDENCE: {high if high is not None else 'none (target not reachable)'}")
    print(f"recommended LOW_CONFIDENCE:  {low if low is not None else 'none (target not reachable)'}")
    if high is not None and low is not None:
        print("\n".join(band_table(clips, high, low)))


if __name__ == "__main__":
    main()
