"""Basic quality check on a lexicon/phrase JSON file.

  python -m ml.translation.qc_lexicon path/to/file.json
"""
import json, sys
from collections import defaultdict

data = json.load(open(sys.argv[1], encoding="utf-8"))
entries = data["entries"]
problems = []

if data.get("entry_count") != len(entries):
    problems.append(f"entry_count says {data.get('entry_count')} but file has {len(entries)}")

seen, by_roh = set(), defaultdict(list)
accented = plain = 0
for e in entries:
    i, roh = e.get("id"), e.get("rohingya_text")
    if i in seen:
        problems.append(f"{i}: duplicate id")
    seen.add(i)
    if not roh or not roh.strip():
        problems.append(f"{i}: missing rohingya_text")
    else:
        if roh != " ".join(roh.split()):
            problems.append(f"{i}: extra spaces in {roh!r}")
        by_roh[roh.strip().lower()].append(i)
        if roh.isascii(): plain += 1
        else: accented += 1
    if not (e.get("source_reference") or {}).get("url"):
        problems.append(f"{i}: missing source url")
    if not e.get("english_meaning", {}).get("word"):
        problems.append(f"{i}: missing english word")
    if not e.get("validation_status"):
        problems.append(f"{i}: missing validation_status")

for roh, ids in by_roh.items():
    if len(ids) > 1:
        problems.append(f"same rohingya {roh!r} used by {', '.join(ids)} (check they really are the same word)")
if accented and plain:
    problems.append(f"mixed spelling style: {accented} entries with accents, {plain} without")

print(f"{len(entries)} entries checked, {len(problems)} problems")
for p in problems:
    print("  -", p)