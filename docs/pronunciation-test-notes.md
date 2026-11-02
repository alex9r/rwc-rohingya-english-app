# Pronunciation scorer: smoke-test notes

> **This is a small smoke test, not an evaluation.** 75 clips in two sets, one model, accent
> labels only on the second set, no human listening. It shows the scorer runs end to end on real recordings and that wrong
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
| Common Voice English (CC0, has accent metadata) | **Used in the second set below**, after you supplied API access (Mozilla Data Collective). |
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


## Second set: Common Voice English with accent labels

50 clips from Mozilla Common Voice Scripted Speech 27.0 (English), **CC0**, fetched through
the Mozilla Data Collective download API. The archive is 95 GB, so I streamed it and stopped
after 628 MB: the metadata files first (`validated.tsv`, which has the self-declared accent),
then the first clips in the archive that matched. Selection: accent label present, 2–10 words,
at least 2 up-votes and no down-votes, at most 8 clips per accent label and 6 for "United
States English" (a baseline). Audio is not committed (`ml/pronunciation/smoke_clips_cv/` is
git-ignored). The manifest is `ml/pronunciation/smoke_manifest_cv.csv`; full results (all 56 rows)
are in [`pronunciation-smoke-results-common-voice.csv`](pronunciation-smoke-results-common-voice.csv).
Common Voice asks that nobody tries to identify speakers: no speaker IDs, ages or genders
are kept, only the accent label.

Same setup as above (`base` model, `MIN_CONFIDENCE = 0.5`). Six clips were also scored against a
wrong sentence.

| Result | |
|---|---|
| Correct target, scored (45 of 50) | mean **97.2**; 38 scored 100; lowest 57 |
| Correct target, **`scoring_unavailable`** (5 of 50) | confidence 0.40–0.49. The transcripts were *near misses*, not garbage (see "Why were 5 clips withheld?"). Had they been scored they would have got 82, 94, 68, 77 and 71. |
| Wrong target (6 pairings) | **0, 0, 0, 0, 0, 0** |

By accent label (scored clips only; **n is 1 to 8 per label, too small to compare groups**):

| Accent label | Scored clips | Mean score |
|---|---|---|
| United States English | 6 | 100 |
| Canadian English | 7 | 100 |
| Hong Kong English | 8 | 99.8 |
| India and South Asia | 7 | 98.6 |
| Scottish English | 7 | 96.4 |
| Southern African | 2 | 90 |
| England English | 7 | 90.1 |
| Filipino | 1 (+1 unavailable) | 100 |

Every clip that did not score 100, or was not scored:

| Accent label (Common Voice) | Target | Heard | Score | Status | Conf. |
|---|---|---|---|---|---|
| Filipino | He could always become a crystal salesman again. | He could always become a crystal-seal's man again. | – | scoring_unavailable | 0.46 |
| Canadian English | Infirm of purpose | Inferm of purpose | – | scoring_unavailable | 0.49 |
| Scottish English | I shall be neither more nor less meritorious | I shall be near the more, no less, oratorious. | – | scoring_unavailable | 0.46 |
| India and South Asia | Agent Keys took out his neuralizer and flashy-thinged the coroner. | Agent keys, took out his Neuralizer and flashed she thing the Corona. | – | scoring_unavailable | 0.46 |
| England English | The boy preferred wine. | The biopreferred wine. | – | scoring_unavailable | 0.40 |
| England English | It spoke of journeys, discoveries, books, and change. | This bulk of journeys, discover a box and change. | 57 | scored | 0.52 |
| England English | The genies were the spirits of good and evil. | The June is all the spirits of good and evil. | 74 | scored | 0.52 |
| Scottish English | The couch cover and hall drapes were blue. | A couch cover and hole drapes were blue. | 75 | scored | 0.61 |
| Southern African | "That baker..." he said to himself, without completing the thought. | That baker you see to himself without completing the thought. | 80 | scored | 0.58 |
| India and South Asia | There's no point in disclaiming, we have everything on tape. | There's no point in describing. We have everything on tape. | 91 | scored | 0.60 |
| Hong Kong English | The thing's not working! | the things not working. | 98 | scored | 0.51 |
| India and South Asia | She bought three cod fishes to cook for dinner. | She bought three cod fishers to cook for dinner. | 99 | scored | 0.58 |


### Why were 5 clips withheld? Transcriber or threshold?

Neither is clearly at fault, and I checked rather than guessed. I re-scored all 50 clips with
the confidence cutoff switched off (`min_confidence=0`) and re-ran the 5 under other
transcriber settings.

- **The transcripts were mostly close.** Heard vs target: "crystal-seal's man" vs "crystal
  salesman"; "Inferm of purpose" vs "Infirm of purpose"; "near the more, no less, oratorious" vs
  "neither more nor less meritorious"; "flashed she thing th…" vs "flashy-thinged"; "biopreferred
  wine" vs "boy preferred wine". Every one is a rare word, a name, or a made-up word
  ("neuralizer", "flashy-thinged"). Whisper is unsure about exactly those, which is what a low
  confidence means.
- **It is not an obvious `transcribe()` bug.** The function returns the text and a confidence that
  match what faster-whisper reports for these clips. Changing its settings does not fix them:
  with VAD off, four of the five confidences got *lower* (0.35–0.48 vs 0.40–0.49); with beam size 1
  the text changed but stayed wrong, confidences 0.37–0.47. Audio level is normal (RMS 0.02–0.06
  vs a median of 0.027 for the other 45). I read the function and found nothing wrong with how it computes confidence, but it is a
  heuristic its own README calls uncalibrated, and I used the
  `base` model, not the default `small`, which would probably be more confident on rare words.
- **The 0.5 threshold is not a clean separator either.** Across all 50 clips, at 0.5 it withheld 5, of
  which 4 would have scored under 90 (good) and 1 would have scored 94 (a loss); and 4 clips with
  scores under 90 (57, 74, 80, 75) still got through at 0.52–0.61. Raising it to 0.6 withholds 18
  clips, 7 of them poor, and still lets one poor clip through. Lowering it to 0.45 stops withholding
  anything useful.

| Threshold | Withheld | Of those, would score under 90 | Poor clips (under 90) still scored |
|---|---|---|---|
| 0.40 | 0 | 0 | 8 |
| 0.45 | 1 | 1 | 7 |
| **0.50** | **5** | **4** | **4** |
| 0.55 | 9 | 6 | 2 |
| 0.60 | 18 | 7 | 1 |

So: confidence does track whether the transcript is wrong (the 8 poor clips have confidences of
0.40–0.61, while 42 of 50 clips that scored 90+ have a median of 0.64), but it also drops
for correct-but-hard text. In the app the targets are short, common words, where rare-word
doubt matters less, so these Common Voice sentences probably overstate the problem. The right
fix is calibration on data like the app's, which is Hari's job, and perhaps a second signal
besides Whisper's own confidence. These are 50 clips; they motivate that work and do not settle a
threshold.

What I take from it, and what I don't:

- The scorer behaves as intended on 50 more clips: low-confidence clips are withheld,
  mismatched sentences score 0, clear matches score high.
- **No accent conclusion can be drawn.** Labels are self-declared and coarse, groups have 1–8
  clips, the clips are read prompts with rare words ("genies", "Neuralizer"), and I did not
  listen to any. The lowest scores (England English, Scottish) look like hard words and
  Whisper `base` errors rather than anything about accent, but that is a guess.
- **Confidence is a weak signal, not a clean gate.** See "Why were 5 clips withheld?" above.
- Common Voice speakers are not Rohingya, and none of this tells us how the app will do for
  them.

## What this does and doesn't show

- **Works end to end** on real mp3 audio (via `ml/speech`'s decoder) with plausible scores:
  clear speech scores high, mismatched sentences score near 0.
- The 14 and 15 on wrong targets come from shared small words ("I", "a"); a short common
  word can earn partial credit by chance.
- **(Tatoeba set only) The low-confidence path was not exercised.** The Common Voice set did exercise it (below). Confidence on these clean
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

## Still worth adding

Common Voice is now covered above. L2-ARCTIC (labelled non-native speakers, non-commercial licence,
download form on the [PSI Lab page](https://psi.engr.tamu.edu/l2-arctic-corpus/)) would add speakers
with a documented first language; I have not downloaded it. To add clips to either set, put the
audio in the git-ignored folder, add manifest rows, and run
`python -m ml.pronunciation.smoke_test <folder> --manifest <manifest.csv>`. Do not commit audio.
