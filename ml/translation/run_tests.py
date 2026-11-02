"""Run tests from tests.csv through translate().

  python -m ml.translation.run_tests                 # english -> rohingya
  python -m ml.translation.run_tests --reverse       # also rohingya -> english
  python -m ml.translation.run_tests --file my.csv   # use another test file

tests.csv columns: english, rohingya, reverse
  - both filled  -> translate() must return the other side
  - rohingya empty -> translate() must say "uncertain" (it should NOT know this)
  - reverse = no -> skip the rohingya->english test for this row (use for rewordings)
Every miss is written to failures.csv.
"""
import argparse, csv, json
from .translate import translate, norm

ap = argparse.ArgumentParser()
ap.add_argument("--file", default=__file__.replace("run_tests.py", "tests.csv"))
ap.add_argument("--reverse", action="store_true", help="also test rohingya -> english")
args = ap.parse_args()

if args.file.lower().endswith(".json"):   # same format as David's / Linxi's files
    with open(args.file, encoding="utf-8") as f:
        tests = [(e["example_sentence"]["english"].strip(),
                  e["example_sentence"]["rohingya"].replace("(not verified)", "").strip(), True)
                 for e in json.load(f)["entries"] if e.get("example_sentence")]
else:                                      # csv: english, rohingya, reverse
    with open(args.file, encoding="utf-8") as f:
        tests = [(r["english"].strip(), r["rohingya"].strip(), r.get("reverse", "yes").strip().lower() != "no")
                 for r in csv.DictReader(f)]

failures, total = [], 0
for en, roh, rev in tests:
    runs = [("en->roh", en, roh or None)]
    if args.reverse and roh and rev:
        runs.append(("roh->en", roh, en))
    for direction, text, want in runs:
        total += 1
        r = translate(text, direction)
        if want is None:
            problem = "false_accept" if r["status"] == "ok" else None
        elif r["status"] != "ok":
            problem = r["status"]            # uncertain / failed
        elif norm(r["translation"]) != norm(want):
            problem = "wrong"
        else:
            problem = None
        if problem:
            failures.append([direction, text, want, r["translation"], r["status"], r["confidence"], problem])

with open("failures.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["direction", "input", "expected", "got", "status", "confidence", "problem"])
    w.writerows(failures)
print(f"{total - len(failures)}/{total} passed, {len(failures)} failed -> failures.csv")
for x in failures:
    print("  FAIL", x[0], repr(x[1]), "->", x[6])