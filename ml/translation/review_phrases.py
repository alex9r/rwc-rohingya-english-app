"""Second-source review + confidence scores for the phrase set.

  python -m ml.translation.review_phrases --gamayun kit5k.tsv --iom db.json
  python -m ml.translation.review_phrases --gamayun kit5k.tsv --iom db.json --file data/collections/groceries.json

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
A phrase in FLAGS (by entry id) or LINE_FLAGS (by kit5k line) is capped at 0.50 until a
native speaker resolves it. Alternative translations are reviewed the same way; in FLAGS
they are keyed "<entry id>/alt<n>".
"""
import argparse, csv, glob, html, json, math, os, re, unicodedata
from difflib import SequenceMatcher

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FILES = [os.path.join(DATA, "rohingya_phrases_38.json")] + sorted(glob.glob(os.path.join(DATA, "collections", "*.json")))
CONF = {"multi_source": 0.95, "single_source": 0.70, "model_fallback": 0.40}
FLAG_CAP = 0.50

# Disagreements found by reading the sources side by side.
FLAGS = {
    "phrase_014": "IOM glosses 'dami' as 'expensive, costly; precious' and 'beshi' means 'very', so "
                  "'Iyan beshi dami' reads as 'This is very expensive', not Gamayun's 'It really is a "
                  "good price'. Ask a native speaker which meaning is right before using it.",
}

# Same idea, keyed by Gamayun kit5k line, so it follows the sentence into any file
# (collections, alternative translations) whatever id it gets there.
LINE_FLAGS = {
    1585: "The Rohingya starts 'Aa*ra baaf' (aa*ra = we/our), so it reads 'Our father works in a "
          "factory', not 'My father'. 'Aa*r baaf' would be 'my father'. Check with a native "
          "speaker whether 'our father' is the normal way to say it.",
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


# Pronouns never confirm a meaning word: with tone marks folded away "aa*ra" (we) looks
# like IOM "ára" (lose), so "We're not lost" was passing on the pronoun.
PRONOUNS = {skel(w) for w in """aa*i aa*ra aa*r aa*rar aa*ttu aa*ttun aa*re aa*rare aa*rattu
aa*rattun tu*i tu*ra tua*r tua*ra tua*re tua*ttu tua*ttun hite hitar hitare hitattu hitattun
hiba hibar hibare hibattu hitara hitarar hitarare""".split()}


def roh_tokens(s):
    """Skeleton tokens, each also with one case/postposition suffix stripped. Pronouns are
    kept (so two-word spans stay aligned) but get no forms, so they never match."""
    out = []
    for w in re.findall(r"[a-z*'’\-]+", s.lower()):
        k = skel(w)
        if len(k) < 2:
            continue
        forms = {k} | {k[: -len(x)] for x in SUFFIXES if k.endswith(x) and len(k) - len(x) >= 3}
        out.append((w, set() if k in PRONOUNS else forms))
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


def load_gamayun(path):
    """English sentence -> (line number, Rohingya). Line 1 is the header."""
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f, delimiter="\t"))[1:]
    out = {}
    for n, (en, roh) in enumerate(rows, start=2):
        out.setdefault(en.strip(), (n, roh.strip()))
    return out


def review_pair(key, en, roh, gamayun, index, corpus_en=None, can_attest=True):
    """Gamayun + IOM check for one English/Rohingya pair.
    Returns (sources_checked, second_review, reference_translation).
    corpus_en: the corpus English to look up, when `en` is a shortened form of it.
    can_attest=False: the phrase is adapted from the corpus line, so it can't count as it."""
    hit = gamayun.get((corpus_en or en).strip())
    attested = can_attest and bool(hit) and hit[1] == roh
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
    flag = FLAGS.get(key) or (LINE_FLAGS.get(hit[0]) if attested else None)
    if flag:
        conf = min(conf, FLAG_CAP)
        iom["result"], iom["note"] = "conflict", flag
    ref = {
        "english": en,
        "rohingya": roh,
        "origin": f"Gamayun kit5k line {hit[0]}" if attested else "model_fallback",
        "confidence": conf,
        "confidence_tier": tier,
        "needs_review": bool(flag) or tier == "model_fallback",
    }
    return [g, SOURCE_2], iom, ref


def review_entry(e, gamayun, index):
    """Fill sources_checked / second_review / reference_translation on an entry, and the
    same three fields on each of its alternative_translations."""
    ex, roh = e["example_sentence"], e["rohingya_text"].strip()
    # The example sentence is the full corpus pair when it matches the phrase itself.
    same = ex["rohingya"].replace("(not verified)", "").strip() == roh
    en = (ex["english"] if same else e["english_meaning"]["word"]).strip()
    e["sources_checked"], e["second_review"], e["reference_translation"] = review_pair(
        e["id"], en, roh, gamayun, index, corpus_en=ex["english"], can_attest=same)
    for i, alt in enumerate(e.get("alternative_translations") or [], start=1):
        alt["sources_checked"], alt["second_review"], alt["reference_translation"] = review_pair(
            f'{e["id"]}/alt{i}', alt["english"].strip(), alt["rohingya"].strip(), gamayun, index)
    return e


def summary(e):
    r = e["reference_translation"]
    alts = e.get("alternative_translations") or []
    tail = f"  (+{len(alts)} alt)" if alts else ""
    return (f'{e["id"]:16} {r["confidence"]:.2f} {r["confidence_tier"]:15} '
            f'IOM {e["second_review"]["result"]:17} {e["second_review"]["key_words_covered"]:>5}  '
            f'{r["english"]}{tail}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamayun", required=True)
    ap.add_argument("--iom", required=True)
    ap.add_argument("--file", nargs="+", default=FILES,
                    help="phrase files to review in place (default: the 38-phrase set and every collection)")
    args = ap.parse_args()

    gamayun = load_gamayun(args.gamayun)
    index = load_iom(args.iom)
    for path in args.file:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"== {os.path.relpath(path)}")
        for e in data["entries"]:
            print(summary(review_entry(e, gamayun, index)))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
