"""Run tests.csv through several translators and write comparison.csv.

  python -m ml.translation.compare_models [--reverse] [--file tests.csv]

To add a model: write a function (text, direction) -> {"translation", "status", "confidence"}
and add it to MODELS below.
"""
import argparse, csv, os
from .translate import translate, norm

MODELS = {
    "lexicon": translate,
    # "model_a": model_a,
    # "model_b": model_b,
}

ap = argparse.ArgumentParser()
ap.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "tests.csv"))
ap.add_argument("--reverse", action="store_true")
args = ap.parse_args()

with open(args.file, encoding="utf-8") as f:
    tests = [(r["english"].strip(), (r.get("rohingya") or "").strip(),
              (r.get("reverse") or "yes").strip().lower() != "no") for r in csv.DictReader(f)]


def grade(r, want):
    if want is None:
        return "false_accept" if r["status"] == "ok" else "correct"
    if r["status"] != "ok":
        return r["status"]
    return "correct" if norm(r["translation"]) == norm(want) else "wrong"


rows, tally = [], {m: {} for m in MODELS}
for en, roh, rev in tests:
    runs = [("en->roh", en, roh or None)]
    if args.reverse and roh and rev:
        runs.append(("roh->en", roh, en))
    for direction, text, want in runs:
        row = [direction, text, want]
        for name, fn in MODELS.items():
            try:
                r = fn(text, direction)
            except Exception:
                r = {"translation": None, "status": "failed", "confidence": 0}
            g = grade(r, want)
            tally[name][g] = tally[name].get(g, 0) + 1
            row += [r["translation"], r["confidence"], g]
        rows.append(row)

header = ["direction", "input", "expected"] + [f"{m}_{c}" for m in MODELS for c in ("got", "confidence", "result")]
with open("comparison.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(rows)
for name, t in tally.items():
    print(f"{name}: {t}")
print(f"{len(rows)} tests -> comparison.csv")