# Plan: collecting pronunciation recordings from Welcome Centre speakers

**Draft for the TPMs; nothing is agreed with the Welcome Centre and nothing is recorded yet.**
Everything stays **unvalidated** until the Centre has reviewed it.

## Why

The scorer ([`ml/pronunciation`](../ml/pronunciation/README.md)) is an ASR match, and we have no recordings
of the people the app serves. Rohingya speakers saying **English** words give us:

- test material for Hari's evaluation and threshold calibration;
- a look at how Whisper treats the accent (it tends to "autocorrect", which flatters scores);
- possibly, later, native-speaker reference audio (`reference_audio_kind: "native_speaker"`), only with
  separate permission.

This is English words by Rohingya speakers, not Rohingya words (which the Centre already supplies).

## What to record

1. **Hero words** first (the TPMs name them; the repo doesn't define them).
2. Then the lexicon's **40 words** (the greetings list, currently `data/rohingya_greetings_40.json`).

3 takes per word, English only, one word per file.

## Format

| | |
|---|---|
| Device | the speaker's phone or a Centre tablet; the app's recorder if possible (it is what the product receives) |
| File | **m4a** or **WAV**, raw, no trimming, normalising or effects |
| Setting | quiet room, door closed, phone a hand's width from the mouth |
| Per file | one word, about 1–2 s, short pause before and after; redo on noise or a cough |
| Name | `<speaker_id>_<word_id>_<take>.m4a`, e.g. `S007_greeting_001_2.m4a`. Never a real name. |

## Consent

Written, plain language, offered in Rohingya and read aloud on request. It must say:

1. **Purpose:** testing how well a computer understands English words said by learners, for the app and
   research on it.
2. **What is kept:** voice recordings and the metadata below; no real names with recordings.
3. **Who sees it:** named project and Centre members; not shared outside, not sold.
4. **Not a test of the person.** We test the app.
5. **Right to withdraw** at any time, no reason needed, no effect on Centre services; recordings are
   deleted on request. Say how and who to ask.
6. **Who holds the data** and **how long** (to be decided with the TPMs and the Centre).
7. **Separate tick-boxes** for optional uses: (a) evaluating the scorer (needed to take part), (b) as
   in-app reference audio, (c) to train or tune a model later, (d) kept after the project ends.

Consent is recorded per speaker before any recording. No under-18s unless a guardian consents and the
Centre agrees.

## Who records

- **Centre-coordinated volunteers.** The Centre decides who is invited; the team does not recruit.
  A few speakers per dialect/background the Centre cares about, not a large number.
- **A named QA person** from the team checks each batch (right word, usable audio, naming, metadata)
  and hands it to the Centre for review. Name: _TBD_.
- **A Centre contact** present or on call to explain consent and stop a session if someone is uncomfortable.

## Metadata

One row per recording, in a CSV kept with the recordings (not in git):

| Field | Notes |
|---|---|
| `speaker_id` | pseudonym (`S007`); the key to a real person is held only by the Centre |
| `dialect_background` | broad, as reported; no more specific than needed |
| `english_experience` | optional, coarse (under 1 y, 1–3 y, over 3 y) |
| `date`, `word_id` / `target_text`, `take` | what was asked, when |
| `device` | optional |
| `consent_version`, `consent_uses` | form version and ticked boxes |
| `status` | `unvalidated` → `reviewed` / `rejected` after Centre review |

Age and gender only if the Centre says the evaluation needs them.

## Storage and validation

Recordings and the CSV **never go in git**. They live in a private, access-limited location run by the
data holder. The Centre reviews each batch (word right, genuine attempt, nothing inappropriate) before use
beyond internal testing; until then results are reported as "from unvalidated recordings".
