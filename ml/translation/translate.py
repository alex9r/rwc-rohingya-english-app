"""translate(text, direction) -> {"translation", "status", "confidence"}

direction: "roh->en" or "en->roh"
status:    "ok" | "uncertain" | "failed"

Looks the input up in the phrase bank (data/*.json). It can't invent
Rohingya: if nothing matches well it returns status "uncertain".
"""
import glob, json, os, re, unicodedata
from difflib import SequenceMatcher

THRESHOLD = 0.85  # higher = safer, but more "uncertain"
# if a word like "not" or "twice" is the only difference, never match
RISKY = {"not", "no", "dont", "cant", "never", "nai", "no", "twice", "once",
         "thrice", "two", "three", "four", "five", "one", "yet"}
DATA = os.path.join(os.path.dirname(__file__), "data")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))  # strip accents
    s = s.replace("(not verified)", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())  # drops * and punctuation


def _load():
    pairs = []  # (english, rohingya)
    for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        for e in json.load(open(path, encoding="utf-8"))["entries"]:
            ex = e.get("example_sentence") or {}
            for en, roh in ((e["english_meaning"]["word"], e.get("rohingya_text")),
                            (ex.get("english"), ex.get("rohingya"))):
                if en and roh:
                    pairs.append((en, roh.replace("(not verified)", "").strip()))
    return pairs


PAIRS = _load()


def translate(text, direction):
    out = lambda t, s, c=0.0: {"translation": t, "status": s, "confidence": round(c, 2)}
    try:
        if direction not in ("en->roh", "roh->en"):
            return out(None, "failed")
        if not isinstance(text, str) or not norm(text):
            return out(None, "failed")
        src, dst = (0, 1) if direction == "en->roh" else (1, 0)
        q = norm(text)
        best, best_score = None, 0.0
        for pair in PAIRS:
            k = norm(pair[src])
            score = SequenceMatcher(None, q, k).ratio()
            if score > best_score and not (set(q.split()) ^ set(k.split())) & RISKY:
                best, best_score = pair, score
        if best and best_score >= THRESHOLD:
            return out(best[dst], "ok", best_score)
        return out(None, "uncertain", best_score)
    except Exception:
        return out(None, "failed")
