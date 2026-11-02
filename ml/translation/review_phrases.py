"""Second-source review + confidence scores for the phrase set.

  python -m ml.translation.review_phrases --gamayun kit5k.tsv --iom db.json

Downloads (not committed, check each licence before redistributing):
  Gamayun kit5k (source 3, CC BY 4.0):
    https://huggingface.co/datasets/CLEAR-Global/Gamayun-kits/resolve/main/parallel/rhg-eng/kit5k.tsv
  IOM Rohingya Dictionary (source 1, CC BY-NC-SA 4.0), the JSON the web app loads:
    https://rohingyadictionary.org/db.json
VOA audio (source 2) has no transcripts, so it can't check text. It's recorded as "not applicable".

For every phrase:
  1. Gamayun: is the exact English/Rohingya pair a line in the corpus?
  2. IOM: are the key English words backed by IOM headwords that appear in the Rohingya
     sentence? (word-level only, IOM has no example sentences). Passes when at least half
     the key words, and at least 2 of them (or 1 for one-word phrases), are covered.
Confidence:
  0.95  multi_source    Gamayun sentence + IOM word check agree
  0.70  single_source   Gamayun sentence only
  0.40  model_fallback  no sentence source, drafted from attested vocabulary
A phrase in FLAGS is capped at 0.50 until a native speaker resolves it.
"""
import argparse, csv, html, json, math, re, unicodedata
from difflib import SequenceMatcher

FILE = __file__.replace("review_phrases.py", "data/rohingya_phrases_38.json")
CONF = {"multi_source": 0.95, "single_source": 0.70, "model_fallback": 0.40}
FLAG_CAP = 0.50

# Disagreements found by reading the sources side by side.
FLAGS = {
    "phrase_014": "IOM glosses 'dami' as 'expensive, costly; precious' and 'beshi' means 'very', so "
                  "'Iyan beshi dami' reads as 'This is very expensive', not Gamayun's 'It really is a "
                  "good price'. Ask a native speaker which meaning is right before using it.",
}

STOP = set("""a an the i me my you your he him his she her it its we our they them their this that
these those is am are was were be been being do does did to of in on at for from by with and or but
if as so not no yet can could will would shall should may might must have has had there here what
how when where who why which some any about up out into than then too very really just ll ve re s t
d m don""".split())
SOURCE_2 = {"source": "VOA Rohingya audio (source 2)", "result": "not_applicable",
            "note": "Audio only, no transcripts, so it can't confirm a written translation."}


def skel(s):
    """Fold Gamayun ASCII spelling and IOM Rohingyalish to one rough sound skeleton."""
    s = str(s).lower().replace("ç", "r")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[*'’\-]", "", s)
    for a, b in (("sh", "s"), ("ch", "s"), ("th", "t"), ("dh", "d"), ("kh", "k"), ("gh", "g"),
                 ("bh", "b"), ("ph", "f"), ("j", "z"), ("c", "s"), ("q", "k"), ("v", "b"),
                 ("y", "i"), ("ee", "i"), ("oo", "u")):
        s = s.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", s)


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def en_words(s):
    return {stem(w) for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP}


# In skeleton form (doubles collapsed): -ottu, -ttu, -ore, -olla, -lla, -loi, -re, -ot, -or, ...
SUFFIXES = ("otu", "tu", "ore", "ola", "la", "loi", "re", "ot", "or", "at", "ar", "e", "r")


def roh_tokens(s):
    """Skeleton tokens, each also with one case/postposition suffix stripped."""
    out = []
    for w in re.findall(r"[a-z*'’\-]+", s.lower()):
        k = skel(w)
        if len(k) < 2:
            continue
        forms = {k} | {k[: -len(x)] for x in SUFFIXES if k.endswith(x) and len(k) - len(x) >= 3}
        out.append((w, forms))
    return out


def close(a, b, fuzzy=True):
    """Same skeleton, or a near miss (one-letter spelling variant) on a longer single word.
    Short words and two-word spans must match exactly: fuzzy hits there were false friends
    (gori ~ gorib 'poor')."""
    if a == b:
        return True
    return (fuzzy and len(b) >= 5 and a[0] == b[0] and abs(len(a) - len(b)) <= 1
            and SequenceMatcher(None, a, b).ratio() >= 0.85)


def load_iom(path):
    index = {}  # skeleton headword -> [(headword, english gloss)]
    for e in json.load(open(path, encoding="utf-8")):
        gloss = []
        for s in json.loads(html.unescape(e["senses"])):
            gs = s["gloss"] if isinstance(s["gloss"], list) else [s["gloss"]]  # single gloss = bare object
            gloss += [g["text"] for g in gs if isinstance(g, dict) and g.get("lang") == "en"]
        if gloss:
            index.setdefault(skel(e["rhglatn"]), []).append((e["rhglatn"], "; ".join(gloss)))
    return index


def iom_review(english, rohingya, index):
    key = en_words(english)
    toks = roh_tokens(rohingya)
    found = []
    for i, (word, forms) in enumerate(toks):
        # unigrams, plus two-word headwords like "dabai haa" (take medicine)
        cands = [(word, forms, True)]
        if i + 1 < len(toks):
            cands.append((f"{word} {toks[i + 1][0]}", {f + n for f in forms for n in toks[i + 1][1]}, False))
        for shown, fs, fuzzy in cands:
            for head_sk, heads in index.items():
                hk = head_sk.replace(" ", "")
                if len(hk) < 3 or not any(close(hk, f, fuzzy) for f in fs):
                    continue
                for head, gloss in heads:
                    # "not fresh" must not confirm "fresh"
                    hit = key & en_words(re.sub(r"\bnot \w+", "", gloss))
                    if hit:
                        found.append({"rohingya": shown, "iom_headword": head, "iom_gloss": gloss,
                                      "english": sorted(hit)})
    covered = sorted({w for f in found for w in f["english"]})
    need = max(math.ceil(len(key) / 2), min(2, len(key)))
    ok = bool(key) and len(covered) >= need
    seen, matches = set(), []
    for f in found:  # one row per headword
        if f["iom_headword"] not in seen:
            seen.add(f["iom_headword"])
            matches.append(f)
    return {
        "source": "IOM Rohingya Dictionary (source 1)",
        "method": "word-level: key English words checked against IOM glosses of words in the Rohingya sentence",
        "result": "corroborated" if ok else ("partial" if covered else "not_corroborated"),
        "key_words_covered": f"{len(covered)}/{len(key)}",
        "covered": covered,
        "missing": sorted(key - set(covered)),
        "matches": matches,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamayun", required=True)
    ap.add_argument("--iom", required=True)
    ap.add_argument("--file", default=FILE)
    args = ap.parse_args()

    with open(args.gamayun, encoding="utf-8") as f:
        rows = list(csv.reader(f, delimiter="\t"))[1:]
    gamayun = {}
    for n, (en, roh) in enumerate(rows, start=2):  # line 1 is the header
        gamayun.setdefault(en.strip(), (n, roh.strip()))
    index = load_iom(args.iom)

    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)
    for e in data["entries"]:
        ex, roh = e["example_sentence"], e["rohingya_text"].strip()
        # The example sentence is the full corpus pair when it matches the phrase itself.
        same = ex["rohingya"].replace("(not verified)", "").strip() == roh
        en = (ex["english"] if same else e["english_meaning"]["word"]).strip()
        hit = gamayun.get(ex["english"].strip())
        attested = same and bool(hit) and hit[1] == roh
        g = {"source": "CLEAR Global Gamayun kit5k (source 3)",
             "result": "sentence_attested" if attested else "not_found"}
        if attested:
            g["line"] = hit[0]
        elif hit:
            g["note"] = f"Phrase is adapted from line {hit[0]}, not a corpus sentence itself: {hit[1]}"
        iom = iom_review(en, roh, index)

        tier = ("multi_source" if iom["result"] == "corroborated" else "single_source") if attested \
            else "model_fallback"
        conf = CONF[tier]
        if e["id"] in FLAGS:
            conf = min(conf, FLAG_CAP)
            iom["result"], iom["note"] = "conflict", FLAGS[e["id"]]

        e["sources_checked"] = [g, SOURCE_2]
        e["second_review"] = iom
        e["reference_translation"] = {
            "english": en,
            "rohingya": roh,
            "origin": f"Gamayun kit5k line {hit[0]}" if attested else "model_fallback",
            "confidence": conf,
            "confidence_tier": tier,
            "needs_review": e["id"] in FLAGS or tier == "model_fallback",
        }
        print(f'{e["id"]}  {conf:.2f} {tier:15} IOM {iom["result"]:17} {iom["key_words_covered"]:>5}  {en}')

    with open(args.file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
