# Pronunciation scorer: smoke-test notes

> **This is a small smoke test, not an evaluation.** 25 clips, one model, no accent labels,
> no human listening. It shows the scorer runs end to end on real recordings and that wrong
> targets score low. It says nothing about accuracy on Rohingya speakers' English. WER and
> threshold calibration are Hari's evaluation.

Run on 2026-11-02 with `ml/pronunciation` (this branch) and `ml/speech` (PR #4),
faster-whisper **`base`** model (int8, CPU), `language="en"`, `MIN_CONFIDENCE = 0.5`,
`fuzzy_threshold = 0.8`.

The `base` model was used, not the default `small`: the `small` weights would not download
from the sandbox (the transfer stalled at 0 bytes), and `base` was already in the local
cache. `small` may transcribe differently.

## Audio used

| | |
|---|---|
| Source | [Tatoeba](https://tatoeba.org) English sentence audio, from the public exports at `downloads.tatoeba.org/exports` (`sentences_with_audio.csv`, `eng_sentences`) |
| Licence | Each clip's licence is listed in the export. **Only clips licensed `CC BY 4.0` were used.** Attribution (speaker username and sentence link) is in [`ml/pronunciation/smoke_manifest.csv`](../ml/pronunciation/smoke_manifest.csv). Tatoeba's terms ask users to respect each item's licence. |
| Selection | 25 clips of 3–7 words, picked with a fixed random seed by `fetch_tatoeba_clips.py` (at most 8 per speaker), and a blocklist that drops distressing or politically loaded sentences (this audience is newcomers). Sentences are therefore random trivia, not app vocabulary. |
| Speakers | 4 Tatoeba contributors (8 clips from each of three, 1 from the fourth). **Accent labels: none.** Tatoeba does not record accent or first language, so the `accent_label` column is `unknown` throughout. |
| Repo | Audio is **not** committed (`ml/pronunciation/smoke_clips/` is git-ignored). Only the manifest (clip IDs, source, licence, attribution, target text) is. |

Tatoeba's terms say its audio is not checked for fidelity to the text or clarity, so a
mismatch can come from the recording itself.

### Sources considered and not used

| Source | Why not |
|---|---|
| Common Voice English (CC0, has accent metadata) | Now hosted on Mozilla Data Collective, which needs an account and agreement to its terms. I did not create accounts or accept terms for you. **Best next source for accented speech; see "What to download" below.** |
| L2-ARCTIC (24 non-native speakers; Hindi, Korean, Mandarin, Spanish, Arabic, Vietnamese L1) | Download is behind a licence form on the PSI Lab page (to be reviewed and accepted by a person); licence reported as non-commercial. Not downloaded. No Rohingya L1, but non-native and labelled. |
| LibriSpeech (CC BY 4.0) | Usable, but the smallest useful archive is hundreds of MB of mostly native audiobook readers, and it has no accent labels; it would not add what Tatoeba doesn't. |
| Speech Accent Archive (George Mason; labelled non-native speakers) | Licence is CC BY-NC-SA 4.0; one long paragraph per speaker, not short sentences. Usable for a private check, not downloaded. |

## Method

1. `fetch_tatoeba_clips.py` picks clips and writes the manifest.
2. `smoke_test.py` transcribes each clip once (`language="en"`) and scores it against its own
   sentence (**correct**). For the first 6 clips it also scores the same transcript against
   the *next* clip's sentence (**wrong target**), to confirm a mismatch scores low.
3. Nothing was tuned after seeing the results.

## Results

Correct targets, 25 clips: **mean 96.7**, median 100, 20 of 25 scored 100, lowest 57.
Wrong targets, 6 pairings: scores **0, 0, 0, 0, 14, 15**. All 31 results had status
`scored`; the confidence of the 25 correct clips ranged 0.52 to 0.92 (mean 0.66), so none
fell under `MIN_CONFIDENCE`.

| # | Clip | Pairing | Target | Heard | Score | Status | Conf. | Likely reason for any shortfall |
|---|---|---|---|---|---|---|---|---|
| 1 | 1247735 | correct | We're a peaceful people. | We're peaceful people | 80 | scored | 0.66 | Whisper dropped "a" (short unstressed word; ASR or speaker, not checked by ear) |
| 2 | 1247735 | wrong target | I reserved a place. | We're peaceful people | 0 | scored | 0.66 | deliberately wrong target (audio of another sentence); low score expected |
| 3 | 1247706 | correct | I reserved a place. | I reserved a place. | 100 | scored | 0.56 | none, clean match |
| 4 | 1247706 | wrong target | I told you all this would happen. | I reserved a place. | 14 | scored | 0.56 | deliberately wrong target (audio of another sentence); low score expected |
| 5 | 1285692 | correct | I told you all this would happen. | I told you all this would happen. | 100 | scored | 0.77 | none, clean match |
| 6 | 1285692 | wrong target | What a pretty flower. | I told you all this would happen. | 0 | scored | 0.77 | deliberately wrong target (audio of another sentence); low score expected |
| 7 | 1129396 | correct | What a pretty flower. | What a pretty flower. | 100 | scored | 0.72 | none, clean match |
| 8 | 1129396 | wrong target | I barely had dinner. | What a pretty flower. | 0 | scored | 0.72 | deliberately wrong target (audio of another sentence); low score expected |
| 9 | 1249195 | correct | I barely had dinner. | I barely had dinner. | 100 | scored | 0.68 | none, clean match |
| 10 | 1249195 | wrong target | This is not a very good example. | I barely had dinner. | 0 | scored | 0.68 | deliberately wrong target (audio of another sentence); low score expected |
| 11 | 1247518 | correct | This is not a very good example. | This is not a very good example | 100 | scored | 0.92 | none, clean match |
| 12 | 1247518 | wrong target | My big sister swims very fast. | This is not a very good example | 15 | scored | 0.92 | deliberately wrong target (audio of another sentence); low score expected |
| 13 | 1285547 | correct | My big sister swims very fast. | My big sister swims very fast | 100 | scored | 0.91 | none, clean match |
| 14 | 1099931 | correct | Huh. I wonder who that's for. | Huh, I wonder who that's for? | 100 | scored | 0.62 | none, clean match |
| 15 | 1285486 | correct | How do archeologists know where to dig? | How do archaeologists know where to dig? | 99 | scored | 0.72 | spelling variant (archeologists / archaeologists), not a speech problem |
| 16 | 1134378 | correct | Esther has posttraumatic stress disorder. | Esther has post-traumatic stress disorder. | 88 | scored | 0.69 | compound written closed vs hyphenated; the scorer splits hyphens, so "posttraumatic" ≠ "post traumatic". Normalisation gap, not speech |
| 17 | 1129409 | correct | He thinks that English sounds abrasive. | He thinks that English sounds abrasive. | 100 | scored | 0.65 | none, clean match |
| 18 | 1249331 | correct | Get off your cross. | Get off your cross | 100 | scored | 0.71 | none, clean match |
| 19 | 1278544 | correct | He heard footsteps. | He heard footsteps. | 100 | scored | 0.53 | none, clean match |
| 20 | 1152970 | correct | I've been to every corner of Europe. | I've been to every corner of Europe. | 100 | scored | 0.67 | none, clean match |
| 21 | 1158055 | correct | Leave me out of this! | Leave me out of this. | 100 | scored | 0.67 | none, clean match |
| 22 | 1158685 | correct | Mary was expelled from the Senate. | Mary was expelled from the Senate. | 100 | scored | 0.67 | none, clean match |
| 23 | 1158036 | correct | He comes here once a month. | He comes here once a month. | 100 | scored | 0.60 | none, clean match |
| 24 | 1278580 | correct | She returned quickly. | She returned quickly. | 100 | scored | 0.61 | none, clean match |
| 25 | 1278147 | correct | She needs this. | She needs this. | 100 | scored | 0.56 | none, clean match |
| 26 | 1278594 | correct | She is unsociable. | She is un-sourgeable. | 57 | scored | 0.52 | Whisper heard a non-word ("un-sourgeable"); either an unusual word for ASR or a real mispronunciation; not checked by ear |
| 27 | 1278553 | correct | He needs assistants. | He needs assistance. | 93 | scored | 0.59 | "assistants" vs "assistance": near-match (partial credit); Whisper chose the commoner word |
| 28 | 1278141 | correct | She seems excited. | She seems excited. | 100 | scored | 0.56 | none, clean match |
| 29 | 1278572 | correct | He apologized profusely. | He apologized profusely. | 100 | scored | 0.65 | none, clean match |
| 30 | 1278595 | correct | He missed class. | He missed class. | 100 | scored | 0.52 | none, clean match |
| 31 | 839086 | correct | The surgeon's suture technique minimizes scarring. | The surgeon's suture technique minimizes scarring. | 100 | scored | 0.77 | none, clean match |

"Likely reason" is a guess from the transcript. I did not listen to the clips.

## What this does and doesn't show

- **Works end to end** on real mp3 audio (via `ml/speech`'s decoder) with plausible scores:
  clear speech scores high, mismatched sentences score near 0.
- The 14 and 15 on wrong targets come from shared small words ("I", "a"); a short common
  word can earn partial credit by chance.
- **The low-confidence path was not exercised on real audio.** Confidence on these clean
  readings sat between 0.52 and 0.92, with eight clips below 0.62, so the 0.5 threshold
  is close to where ordinary clear speech falls. Hari's calibration should look at this
  before anyone trusts 0.5.
- **Two normalisation gaps showed up** (rows 16 and 15): hyphenated vs closed compounds
  ("post-traumatic"), and spelling variants. Both cost points for reasons unrelated to
  speech. Not fixed here; noted for follow-up.

## Known limit: this measures intelligibility, not phonemes

Whisper is trained to produce likely English and tends to **"autocorrect" accented speech**
toward the words it expects. A score of 100 therefore means "Whisper understood the
sentence", not "every sound was correct". The scorer cannot say *which sound* was off,
and it may be more generous to accented speech than a human listener would be. These
clips are mostly clear readings by confident English speakers, which is the easy case. We have no
data yet on Rohingya speakers' English; see the
[recording collection plan](pronunciation-recording-collection-plan.md). Scores stay
`provisional: true`.

## What to download for a better test (needs you)

For an accented-speech test, which is the one that matters for this app:

1. **Common Voice English**, from [Mozilla Data Collective](https://datacollective.mozillafoundation.org/)
   (account and acceptance of the dataset terms needed; CC0; the TSV includes `accents`).
   Take the English `validated.tsv` plus a few dozen `.mp3` clips whose `accents` field is
   non-native (for example South Asian), with short sentences.
2. Or **L2-ARCTIC**, from the [PSI Lab page](https://psi.engr.tamu.edu/l2-arctic-corpus/)
   after reading its licence (non-commercial).

Drop the audio in `ml/pronunciation/smoke_clips/` (git-ignored), add one row per clip to
`ml/pronunciation/smoke_manifest.csv` with `clip_id`, `file`, `source`, `source_url`,
`license`, `attribution`, `target_text`, `accent_label`, and rerun
`python -m ml.pronunciation.smoke_test ml/pronunciation/smoke_clips`. Do not commit the audio.
