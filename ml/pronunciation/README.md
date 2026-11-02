# ml/pronunciation — pronunciation scoring

`score_pronunciation(audio, target_text)` takes a learner's recording and the English
word or sentence they were trying to say, and returns a 0–100 score with short,
encouraging feedback. It is built on [`ml/speech`](../speech/README.md): it transcribes
the clip with `transcribe(audio, language="en")` and compares the transcript to the
target, word by word.

> It measures whether Whisper *understood* the learner
> (intelligibility). It does not look at individual sounds, and the thresholds are
> uncalibrated until Hari's evaluation. Every result carries `provisional: true` and
> `score_basis: "asr_match"`. See [Known limitations](#known-limitations).

## Setup

```bash
pip install -r ml/pronunciation/requirements.txt   # includes ml/speech/requirements.txt
```

`rapidfuzz` does the fuzzy word matching; if it is missing the code falls back to
`difflib` (scores differ slightly). The first real transcription downloads the Whisper
model (see the `ml/speech` README).

## Use

```python
from ml.pronunciation import score_pronunciation

r = score_pronunciation("clip.m4a", "I need a doctor")   # path, bytes, or binary file object
r.score          # 75
r.status         # "scored"
r.to_dict()      # JSON-ready dict for the API response
```

From the command line:

```bash
python -m ml.pronunciation clip.m4a "I need a doctor"
python -m ml.pronunciation clip.m4a "I need a doctor" --model tiny --threshold 0.8
```

## Input

| | |
|---|---|
| `audio` | anything `ml.speech.transcribe` accepts: path, `bytes`, binary file object. m4a/AAC, wav, mp3, ogg, webm, flac. 0.3 s to 60 s, 25 MB max. |
| `target_text` | the word or sentence to practise. Case, punctuation, contractions (`I'm` = `I am`) and digits (`2` = `two`) do not matter. |
| `transcriber` | optional. `f(audio, language) -> TranscriptionResult`. Defaults to `ml.speech.transcribe`. Tests pass a fake. |
| `fuzzy_threshold` | optional, default `0.8`. String similarity (0–1) at which a heard word counts as the target word. |
| `min_confidence` | optional, default `0.5` (`MIN_CONFIDENCE`). Below this ASR confidence nothing is scored. **Uncalibrated.** |

## Output

`to_dict()` returns:

| Field | Type | Notes |
|---|---|---|
| `score` | int 0–100 or `null` | `null` unless `status` is `scored` |
| `max_score` | int | always `100` |
| `status` | string | see below |
| `transcript` | string | what Whisper heard (may be empty) |
| `confidence` | float 0–1 | Whisper confidence from `ml.speech` |
| `matched_words` | list of string | target words that were heard (normalised) |
| `missed_words` | list of string | target words that were not heard |
| `needs_improvement` | list | `{word, heard, issue}`; `issue` is `missed`, `different`, `close` or `extra` (`word` is `null` for `extra`; `heard` is `null` for `missed`) |
| `feedback` | string | short, plain-English, encouraging |
| `feedback_code` | string | stable code for the app to switch on (below) |
| `score_basis` | string | always `"asr_match"` |
| `provisional` | bool | always `true` for now |

Example (heard "I need a dentist" for "I need a doctor"):

```json
{
  "score": 75,
  "max_score": 100,
  "status": "scored",
  "transcript": "I need a dentist",
  "confidence": 0.86,
  "matched_words": ["i", "need", "a"],
  "missed_words": ["doctor"],
  "needs_improvement": [{"word": "doctor", "heard": "dentist", "issue": "different"}],
  "feedback": "Good try! Most of it was clear. Try the highlighted words again.",
  "feedback_code": "good",
  "score_basis": "asr_match",
  "provisional": true
}
```

### Statuses

`score_pronunciation` never raises. Anything that stops a score comes back as a status,
with `score: null`.

| `status` | Meaning | `feedback_code` |
|---|---|---|
| `scored` | a score was computed | `great` (≥90), `good` (≥70), `keep_going` (≥40), `try_again` |
| `scoring_unavailable` | no score: ASR confidence below `min_confidence`, the transcript had no usable words, or the target was empty | `low_confidence`, `unclear_transcript`, `invalid_target` |
| `empty_audio`, `invalid_audio`, `too_short`, `too_long`, `no_speech`, `model_error` | passed straight through from `transcribe()` (see the `ml/speech` README) | same as the status |

`model_error` is the only status that is the server's fault. A wrong argument type
(for example an `int` as the audio) is reported as `invalid_audio`; an unexpected
exception from the transcriber is reported as `model_error`.

## How the score is computed

1. Transcribe with `language="en"`.
2. Normalise both texts: lowercase, strip punctuation, expand contractions, spell out
   digits as words.
3. Align the two word lists (edit-distance alignment). A heard word counts as the
   target word if it is identical, a known homophone (`their`/`there`, `two`/`to`/`too`;
   an ASR cannot tell these apart, so learners are not marked wrong for them), or at least
   `fuzzy_threshold` similar (`doctors` for `doctor` gets partial credit and is flagged
   `close`).
4. `score = 100 × credit ÷ (target words + 0.5 × extra words)`, rounded.

The band cut-offs for `feedback_code`, `MIN_CONFIDENCE`, the fuzzy threshold and the
extra-word weight are constants at the top of `scorer.py`. None of them are calibrated.

## Tests

```bash
python -m pytest ml/pronunciation -q
python -m pytest ml -q            # includes ml/speech
```

The tests use a fake transcriber, so they run offline in well under a second and are safe
for CI. They cover exact match, one wrong word, missing and extra words, punctuation and
case, homophones, an empty target, silent audio (through the real `transcribe()`, which
rejects it before any model loads), low confidence and every pass-through status.

## Smoke test on public audio

A small, informal check on real recordings (not an evaluation):

```bash
python -m ml.pronunciation.fetch_tatoeba_clips --out ml/pronunciation/smoke_clips
python -m ml.pronunciation.smoke_test ml/pronunciation/smoke_clips --out results.csv
```

The audio is git-ignored; only `smoke_manifest.csv` (IDs, licence, attribution, target
text) is committed. Results and caveats are in
[`docs/pronunciation-test-notes.md`](../../docs/pronunciation-test-notes.md).

## Known limitations

- **Intelligibility, not phonemes.** The score says whether Whisper recognised the words.
  It cannot say *which sound* was off.
- **Whisper autocorrects.** It is trained to produce likely English, so accented speech
  is often transcribed as the intended words. Scores can be higher than a human
  listener would give. Do not present the score as a diagnosis.
- **Uncalibrated.** Thresholds and bands are placeholders until Hari's evaluation with
  qualified speakers. Keep `provisional: true` until then.
- Homophone list is small and hand-written; digits are read as cardinals (`2026` becomes
  "two thousand twenty six", not "twenty twenty six").
- Single words are the hardest case: one wrong word is 0, one right word is 100.
