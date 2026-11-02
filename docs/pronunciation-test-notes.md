# Pronunciation scorer: smoke-test notes

> **A small smoke test, not an evaluation.** 75 clips, one model, no human listening. It shows
> the scorer runs on real recordings and that wrong sentences score low. It says nothing about
> Rohingya speakers' English. WER and threshold calibration are Hari's job.

Run 2026-11-02: `ml/pronunciation` on `ml/speech` (PR #4), faster-whisper **`base`** (the default
`small` would not download in the sandbox), `language="en"`, `MIN_CONFIDENCE = 0.5`,
fuzzy threshold 0.8. Audio is not committed; only manifests are.

## Audio used

| Set | Source | Licence | Clips | Accent labels |
|---|---|---|---|---|
| 1 | [Tatoeba](https://tatoeba.org) English audio (public exports) | CC BY 4.0 only (checked per clip) | 25, 3–7 words, 4 speakers | none |
| 2 | Mozilla Common Voice Scripted Speech 27.0 (English), via the Data Collective API | CC0 | 50, 2–10 words | self-declared |

- Manifests: [`smoke_manifest.csv`](../ml/pronunciation/smoke_manifest.csv),
  [`smoke_manifest_cv.csv`](../ml/pronunciation/smoke_manifest_cv.csv). Full results:
  [Tatoeba](pronunciation-smoke-results-tatoeba.csv),
  [Common Voice](pronunciation-smoke-results-common-voice.csv).
- Set 2 comes from a 95 GB archive; I streamed 628 MB. Picked clips with an accent label, at least 2
  up-votes and no down-votes, max 8 per accent (6 for US English as a baseline). Common Voice asks
  that speakers are not identified, so only the accent label is kept.
- Tatoeba does not check its audio against the text, and sentences are random trivia, not app words.
- Method: `smoke_test.py` transcribes each clip once and scores it against its own sentence. Six clips
  per set are also scored against the *next* clip's sentence (wrong target). Nothing was tuned afterwards.

## Results

| | Tatoeba (25) | Common Voice (50) |
|---|---|---|
| Correct target, scored | mean **96.7**, 20 at 100, lowest 57 | 45 scored, mean **97.2**, 38 at 100, lowest 57 |
| Correct target, `scoring_unavailable` | 0 | **5** (confidence 0.40–0.49) |
| Wrong target (6 each) | 0, 0, 0, 0, 14, 15 | 0, 0, 0, 0, 0, 0 |

The 14 and 15 come from shared small words ("I", "a").

**Common Voice by accent** (scored clips; 1–8 per label, too few to compare):

| Accent | n | Mean | | Accent | n | Mean |
|---|---|---|---|---|---|---|
| United States | 6 | 100 | | India / South Asia | 7 | 98.6 |
| Canadian | 7 | 100 | | Scottish | 7 | 96.4 |
| Filipino | 1 | 100 | | England | 7 | 90.1 |
| Hong Kong | 8 | 99.8 | | Southern African | 2 | 90 |

**Every Common Voice clip below 100 or not scored:**

| Accent | Target | Heard | Score | Conf. |
|---|---|---|---|---|
| Filipino | He could always become a crystal salesman again. | …a crystal-seal's man again. | – | 0.46 |
| Canadian | Infirm of purpose | Inferm of purpose | – | 0.49 |
| Scottish | I shall be neither more nor less meritorious | …near the more, no less, oratorious. | – | 0.46 |
| India / S. Asia | Agent Keys took out his neuralizer and flashy-thinged the coroner. | …flashed she thing the Corona. | – | 0.46 |
| England | The boy preferred wine. | The biopreferred wine. | – | 0.40 |
| England | It spoke of journeys, discoveries, books, and change. | This bulk of journeys, discover a box and change. | 57 | 0.52 |
| England | The genies were the spirits of good and evil. | The June is all the spirits… | 74 | 0.52 |
| Scottish | The couch cover and hall drapes were blue. | A couch cover and hole drapes were blue. | 75 | 0.61 |
| Southern African | "That baker..." he said to himself, without completing the thought. | That baker you see to himself… | 80 | 0.58 |
| India / S. Asia | There's no point in disclaiming, we have everything on tape. | …in describing. We have… | 91 | 0.60 |
| Hong Kong | The thing's not working! | the things not working. | 98 | 0.51 |
| India / S. Asia | She bought three cod fishes to cook for dinner. | …cod fishers… | 99 | 0.58 |

**Tatoeba clips below 100** (guesses from the transcript; I listened to none): "We're a peaceful
people" → "We're peaceful people" (80, dropped "a"); "She is unsociable" → "un-sourgeable" (57,
non-word); "posttraumatic" vs "post-traumatic" (88) and "archeologists" vs "archaeologists" (99),
both normalisation gaps, not speech; "assistants" → "assistance" (93).

## Why were 5 clips withheld: transcriber or threshold?

Neither is clearly at fault. I re-scored all 50 with no confidence cutoff and re-ran the 5 with other
transcriber settings.

- **Near misses, not garbage.** Scored anyway they would have got 82, 94, 68, 77, 71. Each has a rare
  word, name or invented word ("infirm", "meritorious", "neuralizer"), which is where Whisper is
  unsure.
- **Not an obvious `transcribe()` bug.** VAD off lowered four of the five confidences (0.35–0.48);
  beam size 1 gave 0.37–0.47 and still-wrong text; audio levels are normal. I read the function and
  found no fault, but its confidence is an uncalibrated heuristic, and `small` would probably be more
  confident than `base`.
- **0.5 is not a clean cutoff.**

| Threshold | Withheld | …of which would score <90 | Poor clips (<90) still scored |
|---|---|---|---|
| 0.40 | 0 | 0 | 8 |
| 0.45 | 1 | 1 | 7 |
| **0.50** | **5** | **4** | **4** |
| 0.55 | 9 | 6 | 2 |
| 0.60 | 18 | 7 | 1 |

At 0.5 one good clip (94) was withheld and four poor ones got through. Confidence tracks
transcript errors but also drops on correct-but-hard text. App targets are short common words, so
these sentences probably overstate the problem. The fix is calibration on app-like data (Hari), and
maybe a second signal besides Whisper's confidence. Fifty clips motivate that; they don't set a
threshold.

## What this does and doesn't show

- Works end to end on real audio: clear speech scores high, wrong sentences near 0, shaky transcripts
  are withheld.
- **No accent conclusion.** Labels are coarse, groups tiny, prompts full of rare words. The lowest
  scores (England, Scottish) look like hard words, not accent, but that is a guess.
- **Intelligibility, not phonemes.** Whisper tends to "autocorrect" accented speech toward expected
  words, so a 100 means it understood the sentence, not that every sound was right, and scores may
  be more generous than a human listener.
- Common Voice speakers are not Rohingya. See the
  [collection plan](pronunciation-recording-collection-plan.md). Scores stay `provisional: true`.

## Adding more clips

Put audio in the git-ignored folder, add manifest rows, then run
`python -m ml.pronunciation.smoke_test <folder> --manifest <manifest.csv> --model base`. L2-ARCTIC
(labelled non-native speakers, non-commercial licence, form on the
[PSI Lab page](https://psi.engr.tamu.edu/l2-arctic-corpus/)) would add documented first languages.
