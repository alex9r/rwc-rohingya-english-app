"""translate(text, direction) -> {"translation", "status", "confidence"}

direction: "roh->en" or "en->roh"
status:    "ok" | "uncertain" | "failed"

Looks the input up in the phrase bank (data/*.json and data/collections/*.json,
including alternative translations). It can't invent
Rohingya: if nothing matches well it returns status "uncertain".
"""
import glob, json, os, re, unicodedata
from difflib import SequenceMatcher

THRESHOLD = 0.85  # higher = safer, but more "uncertain"
DATA = os.path.join(os.path.dirname(__file__), "data")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))  # strip accents
    s = s.replace("(not verified)", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())  # drops * and punctuation


def _load():
    pairs = []  # (english, rohingya)
    # data/*.json plus the domain collections in data/collections/
    for path in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
        for e in json.load(open(path, encoding="utf-8"))["entries"]:
            ex = e.get("example_sentence") or {}
            alts = [(a.get("english"), a.get("rohingya")) for a in e.get("alternative_translations") or []]
            for en, roh in [(e["english_meaning"]["word"], e.get("rohingya_text")),
                            (ex.get("english"), ex.get("rohingya"))] + alts:
                if en and roh:
                    pairs.append((en, roh.replace("(not verified)", "").strip()))
    return pairs


PAIRS = _load()

def _call_model(text, direction):
    """TODO: Implement model fallback once a translation model is selected."""
    return None

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
            if score > best_score:
                best, best_score = pair, score
        if best and best_score >= THRESHOLD:
            return out(best[dst], "ok", best_score)
        model_result = _call_model(text, direction)
        if model_result is not None:
            translation, confidence = model_result
            return out(translation, "ok", confidence)

        return out(None, "uncertain", best_score)

    except Exception:
        return out(None, "failed")