"""Run: python -m ml.translation.test_translate   (from the repo root)"""
import json, os
from .translate import translate, norm, DATA

with open(os.path.join(DATA, "rohingya_phrases_18.json"), encoding="utf-8") as f:
    phrases = json.load(f)["entries"]

# Cases that should NOT match (None = must be "uncertain")
MISSES = ["Where is the library?", "Take your pills with water.", "I have a ticket.",
          "Do you like football?", "", None]

bad = 0
for e in phrases:
    en, roh = e["example_sentence"]["english"], e["example_sentence"]["rohingya"].replace(" (not verified)", "")
    for text, d, want in ((en, "en->roh", roh), (roh, "roh->en", en)):
        r = translate(text, d)
        if r["status"] != "ok" or norm(r["translation"]) != norm(want):
            bad += 1
            print("FAIL", d, repr(text), r)
for text in MISSES:
    r = translate(text, "en->roh")
    if r["status"] == "ok":
        bad += 1
        print("FALSE ACCEPT", repr(text), r)
print("all good" if not bad else f"{bad} problems")
