# Plan: collecting pronunciation recordings from Welcome Centre speakers

**Status: draft for the TPMs. Nothing here has been agreed with the Welcome Centre.**
Nothing is recorded yet. Every recording and label stays **unvalidated** until the
Welcome Centre has reviewed it (README: content added to `data/` is unvalidated until
reviewed).

## Why we need them

The pronunciation scorer ([`ml/pronunciation`](../ml/pronunciation/README.md)) is only an
ASR match, and we have no recordings of the people the app serves. Recordings from
Rohingya speakers saying English words give us:

- real test material for Hari's evaluation and for calibrating the thresholds;
- a way to see how Whisper treats the accent (it tends to "autocorrect", which makes
  scores look better than a human listener would judge);
- later, possibly, reference recordings (`reference_audio_kind: "native_speaker"`), but only
  with separate permission for that use.

These are two different things and must not be mixed up: **English words spoken by Rohingya
speakers** (this plan, for evaluation) vs **Rohingya words** (the lexicon's pronunciations,
which the Centre already provides).

## What to record

| Order | Words | Why |
|---|---|---|
| 1 | The **hero words**, the first few words the app demos (the TPMs to name the list) | Needed first for the demo and first evaluation |
| 2 | The lexicon's **40 words** (the word list used by the app; currently mock data in `app/src/api/mockData.ts`, with `data/lexicon.json` still to land) | Covers the vocabulary learners practise |

Per word, ask each speaker for **3 takes**, so the evaluation can see variation without
tiring anyone. Record the English word only, one word per file. (Short sentences are a
possible later extension.)

## Recording format

| | |
|---|---|
| Device | the speaker's own phone or a Centre tablet, using the Expo app's recorder if possible (that is what the product will receive) or the phone's voice memo app |
| File format | **m4a** (what the app records) or **WAV**; no other conversion needed, `ml/speech` accepts both |
| Setting | a quiet room, door closed, phone about a hand's width from the mouth, no music or TV |
| Per file | **one word per file**, about 1–2 s of speech with a short pause before and after; re-record if there is noise or a cough |
| Naming | `<speaker_id>_<word_id>_<take>.m4a`, for example `S007_word_001_2.m4a` (speaker pseudonym, lexicon id, take number). Never put a real name in a filename. |
| Do not | process, trim hard, normalise or add effects. Keep the raw file. |

## Consent

Written, in plain language, offered in Rohingya (and read aloud to anyone who prefers
that to reading). It must say, in short sentences:

1. **Purpose:** we are testing how well a computer understands English words said by
   people learning English; it is for the app and for research on it.
2. **What we record and keep:** voice recordings of English words, plus the details listed
   under Metadata. No real names are stored with the recordings.
3. **Who sees it:** named members of the project team and the Welcome Centre; not shared
   outside the project, and not used to sell anything.
4. **Not a test of the person.** We are testing the app, not the speaker.
5. **Right to withdraw:** at any time, without giving a reason and without any effect on
   services from the Centre; on request the recordings are deleted and are not used in
   later work. Say how to ask and who to ask.
6. **Who holds the data:** a named holder and a storage location (open question below).
7. **How long** it is kept.
8. **Separate yes/no tick-boxes** for each optional use: (a) evaluating the scorer
   (needed to take part), (b) using the recording as a reference pronunciation in the
   app, (c) using the recording to train or tune a model in the future, (d) keeping it
   after the project ends.

Consent is recorded per speaker, before any recording. Under-18s are out of scope unless a
guardian consents and the Centre agrees.

## Who records

- **Centre-coordinated speakers.** The Welcome Centre decides who is invited; volunteers
  only. No one is recruited by the project team directly. Aim for a few speakers per
  dialect/background the Centre considers important, rather than a large number.
- **A named person for quality assurance** from the project team, to check each batch for
  the right word, usable audio, correct file naming and complete metadata, and to
  hand the batch to the Centre for review. Name: _TBD by the TPMs_.
- **A Centre contact** present or on call during sessions to explain consent and to stop a
  session if a speaker is uncomfortable.

## Metadata

One row per recording, in a CSV kept with the recordings (not in the repo):

| Field | Notes |
|---|---|
| `speaker_id` | pseudonym such as `S007`. The key linking it to a real person is held only by the Centre, not by the project team. |
| `dialect_background` | as reported by the speaker or Centre, in broad terms (for example region/dialect of Rohingya), never more specific than needed |
| `english_experience` | optional, coarse (for example under 1 year, 1–3 years, over 3 years) |
| `date` | recording date |
| `word_id` / `target_text` | what the speaker was asked to say |
| `take` | 1–3 |
| `device` | phone model or "Centre tablet", optional |
| `consent_version`, `consent_uses` | which form version and which optional boxes were ticked |
| `status` | `unvalidated` until Centre review; then `reviewed` or `rejected` |

Age, gender and similar details are only collected if the Centre says they are needed for
the evaluation.

## Storage

Recordings and the metadata CSV **do not go in the git repo** (the repo already ignores
audio for the smoke test; never commit audio, models or keys). They live in a private
location controlled by the data holder, with access limited to named people.
Where, and who holds it, are open questions below.

## Validation

Everything starts as `unvalidated`. The Welcome Centre reviews each batch (is the word
right, is the recording the speaker's intended attempt, anything inappropriate) before it
is used for anything beyond internal testing. Recordings used in the evaluation are
reported as "from unvalidated recordings" until review is finished.

## Open questions for the TPMs

1. **Hero words:** which words, exactly? (Not defined in the repo.)
2. **Who holds the data**, and where is it stored (Centre-controlled drive, university
   storage, other)? Is there a University of Waterloo or WAT.ai ethics/research-data policy
   that applies, and does this need review before we collect anything?
3. **Retention:** how long do we keep recordings, and what happens at the end of the term?
4. **Who from the Centre** coordinates, speaks Rohingya for the consent conversation, and
   reviews the batches? Is a translated consent form available, and who checks the translation?
5. **Compensation or thanks** for speakers: allowed, expected, or not?
6. **Reference audio:** do we ever want speaker recordings as in-app reference audio? If
   yes it needs its own consent and quality bar (see the `native_speaker` kind in the API
   contract).
7. **Who is the named QA person** on the project team?
8. **Sessions:** where and when, and who is present besides the speaker?
