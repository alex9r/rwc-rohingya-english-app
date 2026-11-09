"""Build a recording-prompt list from the Gamayun Rohingya kit (read-only).

Output is a JSONL *manifest template*: every row has the reference transcript from
the kit and empty ``audio`` / ``speaker_id`` / ``verified_by`` to be filled in as
recordings arrive and are checked by a Rohingya speaker. Nothing is written to the
kit. The kit's translations are CLEAR Global's (CC BY 4.0); credit them.

Selection favours short sentences (easier to record and to check) and a fixed seed
so the whole team draws the same set.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path


def build(kit_dir: str | Path, out: str | Path, *, n: int = 100, max_words: int = 8, seed: int = 7) -> int:
    kit = Path(kit_dir)
    with open(kit / "kit5k.tsv", encoding="utf-8", newline="") as f_rhg, \
         open(kit / "core_kit5k.tsv", encoding="utf-8", newline="") as f_core:
        rhg = list(csv.DictReader(f_rhg, delimiter="\t", quoting=csv.QUOTE_NONE))
        core = list(csv.DictReader(f_core, delimiter="\t", quoting=csv.QUOTE_NONE))
    if len(rhg) != len(core):
        raise ValueError("kit5k.tsv and core_kit5k.tsv are not line-aligned")
    pool = [(c["id"], r["eng"], r["rhg"]) for c, r in zip(core, rhg)
            if r["rhg"].strip() and 2 <= len(r["rhg"].split()) <= max_words]
    random.Random(seed).shuffle(pool)
    with open(out, "w", encoding="utf-8") as f:
        for i, (tid, eng, ref) in enumerate(pool[:n], 1):
            f.write(json.dumps({
                "clip_id": f"rhg_{i:04d}", "audio": "", "reference": ref, "language": "rhg",
                "speaker_id": "", "verified_by": "", "source_id": f"tatoeba:{tid}", "english": eng,
            }, ensure_ascii=False) + "\n")
    return min(n, len(pool))
