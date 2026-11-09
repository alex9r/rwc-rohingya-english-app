"""Run: python -m ml.translation.test_translate   (from the repo root)"""
import glob, json, os
from .translate import translate, norm, DATA

FILES = [os.path.join(DATA, "rohingya_phrases_38.json")] +     sorted(glob.glob(os.path.join(DATA, "collections", "*.json")))
pairs = []  # (english, rohingya) every phrase and alternative translation must round-trip
for path in FILES:
    with open(path, encoding="utf-8") as f:
        for e in json.load(f)["entries"]:
            ex = e["example_sentence"]
            pairs.append((ex["english"], ex["rohingya"].replace(" (not verified)", "")))
            pairs += [(a["english"], a["rohingya"]) for a in e.get("alternative_translations") or []]

# Cases that should NOT match (None = must be "uncertain")
MISSES = ["Where is the library?", "Take your pills with water.", "I have a ticket.",
          "Do you like football?", "", None,
          # near misses for the domain collections: same topic, different meaning
          "Where's the nearest pharmacy?", "I promise that I will be late.",
          "My tooth is not giving me pain.", "Would you like tea?", "It isn't likely to rain tomorrow."]

bad = 0
for en, roh in pairs:
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
