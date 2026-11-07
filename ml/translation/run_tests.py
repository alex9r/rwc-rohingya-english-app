
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
from .translate import norm
import importlib

translator = importlib.import_module("ml.translation.translate")

# Disable Gemini during regression tests
translator._call_model = lambda text, direction: None
translate = translator.translate

ap = argparse.ArgumentParser()
ap.add_argument("--file", nargs="+", default=[__file__.replace("run_tests.py", "tests.csv")], 
                 help="one or more .csv / .json test files")
ap.add_argument("--reverse", action="store_true", help="also test rohingya -> english")
args = ap.parse_args()


def load(path):
    """Return [(english, rohingya or "", reverse_ok)] from a .csv or .json file."""
    if not path.lower().endswith(".json"):          # csv: english, rohingya, reverse
        with open(path, encoding="utf-8") as f:
            return [(r["english"].strip(), (r.get("rohingya") or "").strip(),
                     (r.get("reverse") or "yes").strip().lower() != "no")
                    for r in csv.DictReader(f)]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = data["entries"] if isinstance(data, dict) else data
    out = []
    for e in items:
        if "example_sentence" in e:                 # David's / Linxi's format
            en, roh = e["example_sentence"]["english"], e["example_sentence"]["rohingya"]
        else:                                       # simple: {"english": ..., "rohingya": ...}
            en, roh = e["english"], e.get("rohingya")
        out.append((en.strip(), (roh or "").replace("(not verified)", "").strip(),
                    str(e.get("reverse", "yes")).lower() != "no"))
    return out


tests = [t for path in args.file for t in load(path)]
failures, total = [], 0
for en, roh, rev in tests:
    runs = [("en->roh", en, roh or None)]
    if args.reverse and roh and rev:
        runs.append(("roh->en", roh, en))
    for direction, text, want in runs:
        total += 1
        r = translate(text, direction)
        alts = r.get("alternatives") or []
        if want is None:
            problem = "false_accept" if r["status"] == "ok" else None
        elif r["status"] == "uncertain" and any(norm(a) == norm(want) for a in alts):
            problem = None  # ambiguous dictionary match; expected is one alternative
        elif r["status"] != "ok":
            problem = r["status"]            # uncertain / failed
        elif norm(r["translation"]) != norm(want):
            problem = "wrong"
        else:
            problem = None
        if problem:
            failures.append([direction, text, want, r["translation"], r["status"], r["confidence"], problem])

# Explicit coverage: ambiguous (gom) vs non-ambiguous (Hello).
total += 2
r_amb = translate("gom", "roh->en")
if (
    r_amb["status"] != "uncertain"
    or not r_amb.get("alternatives")
    or {norm(a) for a in r_amb["alternatives"]} < {norm("Good"), norm("Fine")}
):
    failures.append(["roh->en", "gom", "Good|Fine", r_amb.get("translation"),
                     r_amb["status"], r_amb["confidence"], "ambiguity"])
r_ok = translate("Hello", "en->roh")
if r_ok["status"] != "ok" or r_ok.get("alternatives") or norm(r_ok["translation"]) != norm("sólam"):
    failures.append(["en->roh", "Hello", "sólam", r_ok.get("translation"),
                     r_ok["status"], r_ok["confidence"], "non_ambiguous"])

with open("failures.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["direction", "input", "expected", "got", "status", "confidence", "problem"])
    w.writerows(failures)
print(f"{total - len(failures)}/{total} passed, {len(failures)} failed -> failures.csv")
for x in failures:
    print("  FAIL", x[0], repr(x[1]), "->", x[6])
