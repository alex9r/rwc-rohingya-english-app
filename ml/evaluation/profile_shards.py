#!/usr/bin/env python3
"""Profile the VOA Rohingya shards: size, duration, coverage, programme.

The dataset card gives no hours, no speaker count and no dialect information,
so this reads the per-clip JSON sidecars and works out what is actually in
each shard. Only the JSON is extracted, the audio stays in the tar.

    python -m ml.evaluation.profile_shards
    python -m ml.evaluation.profile_shards --tars /path/to/train --total 14

Two shards profiled on 26 Oct 2026 gave 10,000 clips and ~27.8 hours each,
every clip from programme vba373, shards running in date order with no overlap
beyond the boundary broadcast. Extrapolated: ~140,000 clips, ~390 hours.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import tarfile
from pathlib import Path


def extract_json(tar_path: Path, dest: Path) -> None:
    if dest.exists() and any(dest.glob("*.json")):
        return
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path) as tf:
        members = [m for m in tf.getmembers() if m.name.endswith(".json")]
        tf.extractall(dest, members=members)


def profile(dest: Path, label: str) -> dict | None:
    recs = []
    for p in sorted(dest.glob("*.json")):
        with open(p) as fh:
            recs.append(json.load(fh))
    if not recs:
        print(f"{label}: no json found")
        return None

    dur = sorted(r["duration"] for r in recs)
    urls = [r.get("download_url", "") for r in recs]
    dates = sorted({m.group(1) for u in urls
                    if (m := re.search(r"/(\d{8})-", u))})
    codes = collections.Counter(m.group(1) for u in urls
                                if (m := re.search(r"-(vba\d+)-", u)))
    per_day = collections.Counter(m.group(1) for u in urls
                                  if (m := re.search(r"/(\d{8})-", u)))

    print(f"\n{'=' * 58}\n{label}\n{'=' * 58}")
    print(f"  clips                {len(recs)}")
    print(f"  hours                {sum(dur) / 3600:.2f}")
    print(f"  duration min/med/max {dur[0]:.1f} / {dur[len(dur) // 2]:.1f} "
          f"/ {dur[-1]:.1f}")
    print(f"  clips under 2s       {sum(1 for x in dur if x < 2)}")
    print(f"  distinct broadcasts  {len(set(urls))}")
    if dates:
        print(f"  date range           {dates[0]} to {dates[-1]} "
              f"({len(dates)} days)")
    print(f"  programme codes      {dict(codes)}")
    if per_day:
        c = sorted(per_day.values())
        print(f"  clips per broadcast  min {c[0]}, median "
              f"{c[len(c) // 2]}, max {c[-1]}")

    return {"clips": len(recs), "hours": sum(dur) / 3600,
            "dates": set(dates), "codes": set(codes), "urls": set(urls)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tars", type=Path,
                   default=Path.home() / "voa_rhg" / "train",
                   help="Folder of downloaded .tar shards")
    p.add_argument("--total", type=int, default=14,
                   help="Shards in the full dataset, for extrapolation")
    a = p.parse_args()

    tars = sorted(a.tars.glob("*.tar"))
    if not tars:
        raise SystemExit(f"No .tar files in {a.tars}. See the README.")

    print(f"{len(tars)} shard(s) downloaded of {a.total}")
    profiles = []
    for t in tars:
        n = int(t.stem.split("-")[-1])
        dest = a.tars.parent / f"x{n}"
        extract_json(t, dest)
        if (pr := profile(dest, f"shard {n}  ({t.name})")):
            profiles.append(pr)

    if len(profiles) < 2:
        return

    print(f"\n{'=' * 58}\nCOMPARISON\n{'=' * 58}")
    codes = set().union(*(p["codes"] for p in profiles))
    print(f"  programme codes      {sorted(codes)}")
    if len(codes) == 1:
        print("  One programme across every sampled shard, so a narrow")
        print("  speaker pool and a single house register.")

    a_, b_ = profiles[0], profiles[1]
    shared = a_["urls"] & b_["urls"]
    print(f"  shared broadcasts    {len(shared)}")
    if len(shared) <= 1:
        print("  Shards partition by broadcast. Any shared broadcast is the")
        print("  one split across the boundary, not duplication.")

    all_dates = sorted(set().union(*(p["dates"] for p in profiles)))
    print(f"  combined date range  {all_dates[0]} to {all_dates[-1]}")

    mh = sum(p["hours"] for p in profiles) / len(profiles)
    mc = sum(p["clips"] for p in profiles) / len(profiles)
    print(f"\n  Extrapolated to {a.total} shards: "
          f"{mc * a.total:,.0f} clips, {mh * a.total:,.0f} hours")
    print("  (assumes the unsampled shards match the sampled ones)")


if __name__ == "__main__":
    main()
