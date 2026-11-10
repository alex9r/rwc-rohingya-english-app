"""Build the domain phrase collections in data/collections/ from Gamayun kit5k.

  python -m ml.translation.build_collections --gamayun kit5k.tsv --iom db.json

(Download links are in review_phrases.py.) Every phrase and every alternative translation
is a real kit5k line, picked by line number in SPEC below. The Rohingya text is copied
from the corpus, never typed here, so a typo can't creep in. Each collection is then run
through the same Gamayun + IOM review as the 38-phrase set (review_phrases.review_entry).

Alternative translations, by relation:
  paraphrase    another corpus line that says the same thing (use either). kit5k has no
                duplicate English lines and few true paraphrases, so this is rare.
  same_pattern  same Rohingya construction with other words; swap the noun or verb
  related       same situation, a different sentence (a natural follow-up or reply)

key_terms lists the spellings of core words that the corpus really uses (Gamayun has no
fixed spelling, e.g. Maherbani-gori / Meherbani-gori / merbanigori for "please"), with
a count of corpus lines and the IOM headword with that meaning (null when IOM has no
entry for the spelling, or only a homograph with a different meaning).

To add a phrase: add its kit5k line number to SPEC and rerun. Don't hand-edit the JSON
output; it is regenerated.
"""
import argparse, json, os, re

from .review_phrases import (DATA, LINE_FLAGS, en_words, load_gamayun, load_iom, review_entry,
                             skel, summary)

OUT = os.path.join(DATA, "collections")
CORPUS = {"title": "CLEAR Global Gamayun kit5k — Rohingya–English parallel corpus",
          "url": "https://huggingface.co/datasets/CLEAR-Global/Gamayun-kits"}

# Phrase ids of the 38-phrase set (rohingya_phrases_38.json) that belong to each domain,
# so the app can show them together without duplicating entries.
EXISTING = {
    "groceries": ["phrase_011", "phrase_012", "phrase_013", "phrase_014", "phrase_032", "phrase_033"],
    "transportation": ["phrase_006", "phrase_007", "phrase_008", "phrase_009", "phrase_010",
                       "phrase_030", "phrase_031"],
    "pharmacy": ["phrase_001", "phrase_002", "phrase_003", "phrase_004", "phrase_005",
                 "phrase_028", "phrase_029"],
    "employment": ["phrase_027", "phrase_034"],
    "everyday": ["phrase_015", "phrase_016", "phrase_017", "phrase_018", "phrase_023",
                 "phrase_025", "phrase_026", "phrase_035"],
}

# domain -> {title, topic, phrases: [(line, subtopic, meaning, use, [(alt line, relation, note)])]}
SPEC = {
    "groceries": {
        "title": "Groceries and Shopping",
        "topic": "Groceries / Shopping",
        "phrases": [
            (4478, "Finding a store", "Asking for the closest large store.",
             "Finding a supermarket or department store in a new neighbourhood.", []),
            (4259, "Finding a store", "Saying you like to shop at the local market.",
             "Small talk about where you buy food; 'bazar' is the market.",
             [(4326, "related", "Saying you shop a lot at one particular store.")]),
            (2723, "Finding a store", "Telling someone a store's closing time.",
             "Understanding opening hours; the pattern '<number>-wa baze' gives the hour.", []),
            (593, "Asking about products", "Asking where someone bought something.",
             "Asking a neighbour or friend where to find a product.", []),
            (106, "Asking about products", "Comparing two items and saying one is better.",
             "Choosing between two pieces of fruit or two products at the market.",
             [(4276, "related", "Pointing out that a piece of fruit is going bad.")]),
            (711, "Food freshness", "Saying eggs spoil quickly in hot weather.",
             "Food storage: keep eggs cold in summer.",
             [(4276, "related", "The same idea for fruit: this apple is starting to rot.")]),
            (1667, "Dietary needs", "Asking why someone doesn't eat pork.",
             "Pork vocabulary ('shuworor gusto') for halal food questions; listen for it in replies.",
             []),
            (1508, "Dietary needs", "Saying you prefer fish to meat.",
             "Telling a host or shop worker what you like to eat.",
             [(1158, "related", "Saying how often you eat fish: every week.")]),
            (1775, "Food and drink", "Offering someone coffee.",
             "Offering or being offered a drink.",
             [(365, "same_pattern", "Same 'Tu*i ... haiba ne?' (would you like to eat/drink ...?) "
                                    "construction, with fruit instead of coffee. Swap the food word."),
              (171, "related", "Being offered tea or coffee; 'saa' is tea.")]),
            (1401, "Food and drink", "Politely asking someone to pass the salt.",
             "Asking for something at the table; 'merbanigori' is 'please'.", []),
            (4998, "Food and drink", "Suggesting you go and eat something.",
             "Inviting a friend or family member to eat.",
             [(402, "related", "Suggesting you eat out tonight.")]),
            (673, "Money and paying", "Saying you still have some money with you.",
             "Checking whether you can afford more items; 'thiya*' is money.",
             [(273, "related", "The opposite: you don't have enough money (also phrase_033).")]),
            (1967, "Money and paying", "Saying the machine rejected your credit card.",
             "Explaining a card problem at a cash machine or checkout.", []),
            (4960, "Money and paying", "Saying what you bought at a shop and how much.",
             "Describing a purchase; 'kinni' is 'bought'.",
             [(4326, "related", "Saying you buy a lot of things at that store.")]),
        ],
    },
    "transportation": {
        "title": "Transportation",
        "topic": "Transportation",
        "phrases": [
            (2368, "On the bus", "Asking passengers to stay seated until the bus has stopped.",
             "Understanding a driver's or recorded announcement on a bus.",
             [(3962, "same_pattern", "The same announcement on a plane. Note the two spellings of "
                                     "'please' in the corpus: 'maherbanigori' and 'merbani gori'.")]),
            (1863, "On the bus", "Telling someone you kept a seat for them.",
             "Travelling with family or friends; 'boiRoni' is a seat.", []),
            (1204, "On the train", "Saying there are very few passengers on the train.",
             "Talking about how busy a train is.", []),
            (1729, "On the train", "Warning someone they will miss the train if they don't hurry.",
             "Getting to the station on time; 'tora-tori' is 'quickly/hurry'.",
             [(454, "related", "After missing it: 'I've missed my train' (also phrase_030)."),
              (1737, "same_pattern", "Same 'rel gan lot no'fa' (miss the train) wording, about "
                                     "someone else: 'Perhaps he missed the train.'")]),
            (4502, "Schedules", "Saying when your airport shuttle bus leaves.",
             "Giving a departure time; '6'wa baze' is six o'clock.", []),
            (476, "Air travel", "Asking whether you can board this plane.",
             "Checking you are at the right gate.", []),
            (3962, "Air travel", "Asking passengers to stay seated until the plane reaches the gate.",
             "Understanding a cabin announcement after landing.",
             [(2368, "same_pattern", "The same announcement on a bus.")]),
            (2207, "Directions", "Saying the shopping centre is a mile further down the road.",
             "Giving or understanding directions with a distance.", []),
            (1298, "Directions", "Saying you can easily walk there from here.",
             "Deciding whether you need transport or can walk.",
             [(1394, "related", "Suggesting you go for a walk.")]),
            (555, "Directions", "Reassuring someone that you are not lost.",
             "Finding your way; 'a*zi zai' is 'get lost'.",
             [(6, "related", "Worrying that you will get lost (the corpus line names Adam).")]),
            (2720, "Directions", "Saying a map is available if you ask for one.",
             "Asking for a map at a station or information desk.", []),
            (2570, "Road safety", "Telling someone to wait for the green light before crossing.",
             "Crossing the street safely at traffic lights.",
             [(2962, "related", "Someone crossing on foot at the red light ('lal batti').")]),
            (2030, "Road safety", "Warning not to cross the tracks while the alarm is ringing.",
             "Safety at railway level crossings.", []),
        ],
    },
    "pharmacy": {
        "title": "Pharmacy and Health",
        "topic": "Pharmacy / Medical",
        "phrases": [
            (997, "Describing symptoms", "Saying you had a headache and couldn't do something.",
             "Explaining a headache to a pharmacist, doctor or employer; 'mata ho*rail' is a headache.",
             []),
            (2260, "Describing symptoms", "Saying your tooth hurts very badly.",
             "Describing toothache at a dentist or pharmacy.",
             [(803, "related", "The word for dentist, 'dator dhattor' (tooth doctor).")]),
            (2590, "Describing symptoms", "Saying your stomach started to hurt after eating.",
             "Describing a stomach ache and what caused it; 'feth' is stomach.", []),
            (4524, "Describing symptoms", "Saying a shooting pain goes into your right leg.",
             "Describing where pain is and how it spreads.", []),
            (4446, "Describing symptoms", "Saying you taste blood when you cough.",
             "Reporting a serious symptom; 'lo' / 'low' is blood.", []),
            (267, "Describing symptoms", "Saying someone got tired quickly.",
             "Describing tiredness or weakness; 'oran' is tired.", []),
            (2494, "Injuries", "Saying a grandmother hurt her leg in a fall.",
             "Reporting a fall; 'duk faiye' is 'got hurt'.",
             [(2687, "related", "Saying you injured yourself during exercise.")]),
            (3226, "Injuries", "Asking someone to stop the bleeding from a wound.",
             "First aid: asking for help with bleeding.", []),
            (3265, "Injuries", "Saying there is a first aid kit in the bathroom.",
             "First aid at home; 'foilar dabai' is first-aid medicine.", []),
            (1377, "Talking to the doctor", "Asking the doctor what they think.",
             "Asking a doctor or pharmacist for their opinion; 'dhath'thor shab' is a polite 'doctor'.",
             [(228, "related", "Another corpus spelling of doctor: 'dhattor'.")]),
            (3026, "Talking to the doctor", "Asking whether a treatment will hurt.",
             "Asking about pain before a treatment.", []),
            (3606, "Health advice", "Saying that stress causes high blood pressure.",
             "Understanding health advice about blood pressure.", []),
            (3101, "Health advice", "Saying regular exercise is very good for your health.",
             "Understanding health advice; 'sehet' is health.",
             [(2572, "related", "The opposite: lack of exercise can harm your health.")]),
        ],
    },
    "employment": {
        "title": "Employment and Work",
        "topic": "Employment",
        "phrases": [
            (4383, "Looking for work", "Saying you applied for a job.",
             "Talking about a job application; 'dorhas' is an application.", []),
            (1189, "Looking for work", "Politely saying you have no experience.",
             "Honest answer in a job interview; starts with 'Maaf sai' (sorry).",
             [(684, "related", "Saying you are not used to the job yet.")]),
            (890, "Looking for work", "Saying you used to have a job somewhere.",
             "Describing past work. The corpus line says Australia; swap in your own place name.",
             []),
            (969, "Looking for work", "Saying you don't want to work as a waiter.",
             "Saying what kind of work you want or don't want; 'hisabe' is 'as'.", []),
            (1744, "Small talk", "Asking where someone works.",
             "Getting to know a co-worker, neighbour or caseworker.",
             [(112, "related", "Saying where a family member works (at the bank).")]),
            (1585, "Small talk", "Saying a family member works in a factory.",
             "Talking about your family's work; 'harhana' is a factory.", []),
            (1146, "Hours and schedule", "Saying you don't work on weekends.",
             "Telling an employer which days you are available.", []),
            (1049, "Hours and schedule", "Saying you'll be busy until 2:30.",
             "Telling someone when you'll be free; 'arai-wa' is half past two.", []),
            (1135, "Hours and schedule", "Asking whether you can go home early.",
             "Asking a supervisor for permission to leave early.", []),
            (1051, "Being on time", "Promising not to be late.",
             "Reassuring an employer; 'deri' is late.",
             [(1844, "same_pattern", "Same promise, reported about someone else.")]),
            (1216, "Being on time", "Saying it looks like you'll be late again.",
             "Warning your workplace that you're running late.",
             [(1757, "related", "Saying you knew you would be late.")]),
            (1721, "At work", "Asking a co-worker whether they have a meeting.",
             "Workplace small talk; the corpus uses both 'meething' and 'muzolish' for meeting.",
             [(540, "related", "Asking how long the meeting was ('muzolish').")]),
            (916, "At work", "Inviting someone back to your office.",
             "Workplace conversation; 'obish' is office.", []),
            (1717, "At work", "Saying you have a huge amount of work.",
             "Telling someone you're very busy.",
             [(840, "related", "Saying you did your job.")]),
            (263, "Pay", "Saying you got a big pay raise.",
             "Talking about pay; 'tolof' / 'tolob' is salary.", []),
        ],
    },
    "everyday": {
        "title": "Everyday Interactions",
        "topic": "Everyday",
        "phrases": [
            (42, "Understanding", "Saying you don't understand what the problem is.",
             "Asking for clarification at an office, school or clinic; 'buzi no'farir' is 'can't understand'.",
             [(1864, "related", "Another 'didn't understand' sentence: what he wanted to tell me.")]),
            (616, "Understanding", "Asking what something means.",
             "Asking about a word, letter or sign you don't know; 'maani' is meaning.", []),
            (1843, "Understanding", "Asking someone to explain something to you.",
             "Asking for help with a form or instructions.", []),
            (2357, "Asking for help", "Offering help to a woman politely.",
             "A staff member offering help; you may hear this at a counter.",
             [(1360, "related", "Offering to come and help.")]),
            (1728, "Asking for help", "Saying you can't do this without their help.",
             "Thanking or asking a caseworker or volunteer for help.", []),
            (4966, "Thanking", "Thanking someone for their guidance.",
             "Thanking a teacher, caseworker or mentor.",
             [(4645, "related", "Another thank-you, for someone's courtesy. Uses the longer "
                                   "'aa*i tua*re shukuriya zanai' (I thank you) form."),
              (2586, "same_pattern", "Same '... iyanolla shukuriya' (thanks for ...) form, for a card."),
              (4230, "same_pattern", "Same form: thank you for the endless support.")]),
            (2966, "Polite requests", "Asking someone to excuse you for a moment.",
             "Stepping away politely.", []),
            (734, "Home and visitors", "Inviting guests in and telling them to make themselves at home.",
             "Welcoming visitors into your home.", []),
            (1808, "Home and visitors", "Asking when someone's rent is due.",
             "Housing: 'keriya' is rent.", []),
            (1461, "Home and visitors", "Asking who is knocking at the door.",
             "Answering the door.", []),
            (1162, "Small talk", "Asking where in Canada someone is from.",
             "Small talk with neighbours and new acquaintances.", []),
            (418, "Small talk", "Asking when someone started learning English.",
             "Talking about English classes.",
             [(1476, "related", "Saying English isn't easy to master.")]),
            (1294, "Weather", "Saying the weather is really bad.",
             "Small talk about the weather; 'musom' is weather.", []),
            (732, "Weather", "Saying it will probably rain tomorrow.",
             "Planning around the weather; 'zor' is rain.",
             [(1760, "related", "The opposite: the chance of rain is low.")]),
            (1708, "Phone", "Asking someone to call you after they talk to others.",
             "Arranging a phone call; 'kol mara' is to call.",
             [(674, "same_pattern", "Same 'kol mara' (call) verb: she says she will call you later."),
              (976, "related", "Asking whether you can call later (also phrase_035).")]),
            (2950, "Phone", "Asking whether someone charged their phone battery.",
             "Everyday phone vocabulary; 'mubil' / 'mubail' is mobile phone.", []),
            (972, "Time", "Saying you need more time.",
             "Asking for more time with a form, task or decision.", []),
        ],
    },
}

# concept -> (english gloss, [spellings to look for in the Rohingya side of the corpus])
KEY_TERMS = {
    "groceries": [
        ("money", ["thiya*"]),
        ("price", ["dam"]),
        ("buy", ["kini", "kinni", "kinnil", "kine"]),
        ("store / shop", ["duan", "duwan"]),
        ("market", ["bazar", "marketh"]),
        ("fish", ["mas"]),
        ("meat", ["gusso", "gussot", "gusto"]),
        ("egg", ["andha", "dhim"]),
        ("fruit", ["gula-gala"]),
        ("coffee", ["coffee", "kofi"]),
        ("tea", ["saa"]),
        ("salt", ["nun"]),
    ],
    "transportation": [
        ("bus", ["bas", "baas", "bus"]),
        ("train", ["rel"]),
        ("ticket", ["thiket", "thiketh"]),
        ("station", ["estheshon", "eshtheshon", "estheshen"]),
        ("car / vehicle", ["gari", "kar", "kaar"]),
        ("road / way", ["rasta", "rassa"]),
        ("plane", ["felin", "peling", "plin", "filing"]),
        ("seat", ["boiRoni"]),
        ("walk", ["a*Ri"]),
        ("quickly / hurry", ["tora-tori"]),
    ],
    "pharmacy": [
        ("medicine", ["dabai"]),
        ("pill", ["bori"]),
        ("doctor", ["dhath'thor", "dhattor"]),
        ("hospital", ["dhath'tha-hana", "dhath'tha-hanat"]),
        ("sick / illness", ["biaram"]),
        ("pain", ["bish"]),
        ("get hurt / pain / suffer", ["duk"]),
        ("wound / injury", ["zohom"]),
        ("blood", ["lo", "low", "lou"]),
        ("health", ["sehet", "aramiyot"]),
        ("stomach / belly", ["feth"]),
        ("tired / fatigue", ["oran"]),
    ],
    "employment": [
        ("work / job", ["ham"]),
        ("job / post", ["so*ri", "so*rit"]),
        ("salary", ["tolob", "tolof"]),
        ("office", ["obish", "ofis", "ofisot"]),
        ("meeting", ["muzolish", "muzilish", "meething"]),
        ("company", ["kumfani"]),
        ("factory", ["harhana", "harhanat"]),
        ("late", ["deri"]),
        ("busy", ["zamila", "zamilat", "duadi", "duwadi"]),
        ("experience", ["tojuruba"]),
    ],
    "everyday": [
        ("please", ["Maherbani-gori", "Meherbani-gori", "maherbanigori", "merbanigori", "merbani gori"]),
        ("thank you", ["shukuriya", "shukuria"]),
        ("sorry / pardon / forgive", ["maf"]),
        ("help", ["modot"]),
        ("understand", ["buzi", "buza"]),
        ("call (phone)", ["kol"]),
        ("mobile phone", ["mubail", "mubil"]),
        ("time", ["shomoi", "thaim", "okto"]),
        ("rent", ["keriya"]),
        ("weather", ["musom", "mousom", "abuhaba"]),
        ("rain", ["zor"]),
        ("tomorrow", ["ayedde-hailla", "ayedde hailla", "ayedde-haliya"]),
    ],
}


def tokens(s):
    return re.findall(r"[a-z*'’\-]+", s.lower())


def count_lines(term, rohingya_lines):
    """kit5k line numbers whose Rohingya contains `term` as whole word(s) (a case/postposition
    suffix like -ot, -or, -re is allowed after it)."""
    want = term.lower().split()
    hits = []
    for n, roh in rohingya_lines:
        t = tokens(roh)
        for i in range(len(t) - len(want) + 1):
            window = t[i:i + len(want)]
            if window[:-1] == want[:-1] and re.fullmatch(
                    re.escape(want[-1]) + r"(?:-?(?:ot|or|re|e|r|wa|gwa|gan|in|lla|olla|ottu|ttu|at))?",
                    window[-1]):
                hits.append(n)
                break
    return hits


def key_terms(domain, rohingya_lines, index):
    out = []
    for gloss, spellings in KEY_TERMS[domain]:
        forms = []
        for sp in spellings:
            lines = count_lines(sp, rohingya_lines)
            # Tone marks are folded away, so a spelling can hit several IOM headwords
            # (zor 'fever' / zór 'rain'). Only take a sense whose gloss names the concept.
            senses = index.get(skel(sp).replace(" ", ""), []) + index.get(skel(sp), [])
            want = en_words(gloss)
            iom = next(((h, g) for h, g in senses if want & en_words(g)), None)
            forms.append({
                "rohingya": sp,
                "corpus_lines": len(lines),
                "corpus_examples": lines[:3],
                "iom_headword": iom[0] if iom else None,
                "iom_gloss": iom[1][:80] if iom else None,
            })
        out.append({"english": gloss, "spellings": forms})
    return out


def sentence_type(en):
    s = en.strip()
    if s.endswith("?"):
        return "Interrogative sentence"
    first = re.findall(r"[A-Za-z']+", s)[0].lower()
    if first in {"please", "wait", "do", "don't", "call", "take", "c'mon", "come", "send", "put"}:
        return "Imperative sentence"
    return "Exclamatory sentence" if s.endswith("!") else "Declarative sentence"


def entry(eid, domain, topic, line, subtopic, meaning, use, alts, rows):
    en, roh = rows[line]
    e = {
        "id": eid,
        "rohingya_text": roh,
        "english_meaning": {"word": en.rstrip(".!"), "definition": meaning,
                            "explanation": f"Practical phrase for {topic.lower()}: {use[0].lower()}{use[1:]}"},
        "part_of_speech": sentence_type(en),
        "source_reference": {**CORPUS, "lookup_term": en, "evidence": "source_attested"},
        "related_topic": topic,
        "subtopic": subtopic,
        "example_sentence": {
            "english": en, "rohingya": roh,
            "translation_verification": "source_attested",
            "example_origin": "corpus_direct",
            "example_source_url": CORPUS["url"],
            "review_note": f"Directly attested in CLEAR Global Gamayun kit5k corpus (line {line}). "
                           "Professional translation by CLEAR Global translators. Pending native-speaker "
                           f"review. Corpus line: {line}",
        },
        "alternative_translations": [
            {"english": rows[n][0], "rohingya": rows[n][1], "relation": rel, "note": note,
             "corpus_line": n}
            for n, rel, note in alts
        ],
        "alternative_spellings_scripts": {"latin": [], "other_scripts": None},
        "audio_pronunciation": None,
        "image": None,
        "different_forms": [],
        "validation_status": "source_attested_pending_native_review",
    }
    if line in LINE_FLAGS:
        e["example_sentence"]["review_note"] += " FLAG: " + LINE_FLAGS[line]
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamayun", required=True)
    ap.add_argument("--iom", required=True)
    args = ap.parse_args()

    gamayun = load_gamayun(args.gamayun)
    rows = {n: (en, roh) for en, (n, roh) in gamayun.items()}
    rohingya_lines = sorted((n, roh) for n, (_, roh) in rows.items())
    index = load_iom(args.iom)
    os.makedirs(OUT, exist_ok=True)

    for domain, spec in SPEC.items():
        entries = []
        for i, (line, sub, meaning, use, alts) in enumerate(spec["phrases"], start=1):
            eid = f"{domain}_{i:03d}"
            entries.append(entry(eid, domain, spec["topic"], line, sub, meaning, use, alts, rows))

        print(f"== {domain}")
        for e in entries:
            print(summary(review_entry(e, gamayun, index)))
        n_alt = sum(len(e["alternative_translations"]) for e in entries)
        data = {
            "dataset": f"Rohingya Settlement Phrases — {spec['title']}",
            "schema_version": "draft-1",
            "collection": domain,
            "entry_count": len(entries),
            "alternative_count": n_alt,
            "source_priority": "https://www.rohingyalanguage.com/download",
            "notes": [
                f"{len(entries)} {spec['title'].lower()} phrases for Rohingya newcomers to Canada, "
                f"with {n_alt} alternative translations. Every phrase and alternative is a sentence "
                "taken directly from the CLEAR Global Gamayun kit5k corpus (CC BY 4.0); none are drafted.",
                "Same entry schema as rohingya_phrases_38.json, plus 'subtopic' and "
                "'alternative_translations' (each with relation, corpus_line, sources_checked, "
                "second_review and reference_translation).",
                "Relations: paraphrase = same meaning, use either; same_pattern = same Rohingya "
                "construction with different words; related = same situation, different sentence.",
                "key_terms: spellings of core words the corpus actually uses, with corpus line counts "
                "and the IOM Rohingya Dictionary headword (CC BY-NC-SA 4.0, short glosses only).",
                "Confidence: 0.95 = Gamayun sentence + IOM word check agree; 0.70 = Gamayun sentence only; "
                "capped at 0.50 where the sources disagree. All entries need native-speaker review before "
                "use as gold evaluation data.",
                "Generated by ml/translation/build_collections.py. Edit SPEC there and rerun; "
                "don't hand-edit this file.",
            ],
            "related_existing_entries": {"file": "rohingya_phrases_38.json", "ids": EXISTING[domain]},
            "key_terms": key_terms(domain, rohingya_lines, index),
            "entries": entries,
        }
        with open(os.path.join(OUT, f"{domain}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
