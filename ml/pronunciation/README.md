# ml/pronunciation: pronunciation scoring

`score_pronunciation(audio, target_text)` takes a learner's recording and the English word or
sentence they tried to say, and returns a 0–100 score with short, encouraging feedback. It
transcribes the clip with [`ml/speech`](../speech/README.md) (`language="en"`) and compares the
transcript to the target, word by word.

> It measures whether Whisper *understood* the learner (intelligibility), not individual sounds, and
> the thresholds are uncalibrated until Hari's evaluation. Every result carries `provisional: true`
> and `score_basis: "asr_match"`. See [Known limitations](#known-limitations).

## Run

From the repo root, Python 3.10+:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r ml/pronunciation/requirements.txt        # includes ml/speech's requirements
python -m pytest ml -q                                   # offline, no model download
python -m ml.pronunciation clip.m4a "I need a doctor" --model base   # first run downloads the model
python -m ml.pronunciation.smoke_test ml/pronunciation/smoke_clips_cv \
  --manifest ml/pronunciation/smoke_manifest_cv.csv --model base
```

The backend doesn't exist yet. When it lands, use the same venv so it can import `ml.*` from the repo root.

CLI options: `--model` (faster-whisper size), `--threshold` (fuzzy match, default 0.8),
`--min-confidence` (default 0.5). `rapidfuzz` does the matching; without it the code falls back to
`difflib` (slightly different scores).

```python
from ml.pronunciation import score_pronunciation

r = score_pronunciation("clip.m4a", "I need a doctor")   # path, bytes, or binary file object
r.score, r.status                                         # 75, "scored"
r.to_dict()                                               # JSON-ready dict for the API
```

## Input

| | |
|---|---|
| `audio` | anything `ml.speech.transcribe` accepts (path, `bytes`, file object; m4a, wav, mp3, ogg, webm, flac), 0.3–60 s, 25 MB max |
| `target_text` | word or sentence to practise; case, punctuation, contractions (`I'm` = `I am`) and digits (`2` = `two`) don't matter |
| `transcriber` | optional `f(audio, language) -> TranscriptionResult`; defaults to `ml.speech.transcribe`; tests pass a fake |
| `fuzzy_threshold` | default `0.8`: string similarity (0–1) at which a heard word counts as the target |
| `min_confidence` | default `0.5`: below this ASR confidence nothing is scored. **Uncalibrated.** |

## Output

`to_dict()` returns:

| Field | Notes |
|---|---|
| `score` | int 0–100, `null` unless `status` is `scored` |
| `max_score` | always `100` |
| `status` | see below |
| `transcript`, `confidence` | what Whisper heard; its 0–1 confidence |
| `matched_words`, `missed_words` | normalised target words heard / not heard |
| `needs_improvement` | `{word, heard, issue}`; `issue` is `missed`, `different`, `close` or `extra` (`word` null for `extra`, `heard` null for `missed`) |
| `feedback`, `feedback_code` | short plain-English message; stable code for the app to switch on |
| `score_basis`, `provisional` | always `"asr_match"` and `true` for now |

```json
{
  "score": 75, "max_score": 100, "status": "scored",
  "transcript": "I need a dentist", "confidence": 0.86,
  "matched_words": ["i", "need", "a"], "missed_words": ["doctor"],
  "needs_improvement": [{"word": "doctor", "heard": "dentist", "issue": "different"}],
  "feedback": "Good try! Most of it was clear. Try the highlighted words again.",
  "feedback_code": "good", "score_basis": "asr_match", "provisional": true
}
```

### Statuses

It never raises; anything that stops a score comes back as a status with `score: null`.

| `status` | Meaning | `feedback_code` |
|---|---|---|
| `scored` | scored | `great` (≥90), `good` (≥70), `keep_going` (≥40), `try_again` |
| `scoring_unavailable` | confidence below `min_confidence`, no usable words, or empty target | `low_confidence`, `unclear_transcript`, `invalid_target` |
| `empty_audio`, `invalid_audio`, `too_short`, `too_long`, `no_speech`, `model_error` | passed through from `transcribe()` | same as the status |

Only `model_error` is the server's fault. Any exception from the transcriber, including a wrong argument
type (a bug in our code, not the learner's recording), counts as `model_error`.

## How the score is computed

1. Transcribe with `language="en"`.
2. Normalise both texts: lowercase, strip punctuation, expand contractions, spell out digits.
3. Align the word lists (edit distance). A heard word matches if identical, a known homophone
   (`their`/`there`; an ASR can't tell them apart), or at least `fuzzy_threshold` similar
   (`doctors` for `doctor` gets partial credit and is flagged `close`).
4. `score = 100 × credit ÷ (target words + 0.5 × extra words)`, rounded.

The band cut-offs, `MIN_CONFIDENCE`, the fuzzy threshold and the extra-word weight are constants at the
top of `scorer.py`. None are calibrated.

## Tests and smoke test

The unit tests use a fake transcriber, so they run offline in under a second and are safe for CI. They
cover exact match, one wrong word, missing and extra words, punctuation and case, homophones, empty
target, silent audio, low confidence and every pass-through status.

The smoke test scores real public clips (Tatoeba, Common Voice). Audio is git-ignored; only the
manifests are committed. To fetch the Tatoeba set:
`python -m ml.pronunciation.fetch_tatoeba_clips --out ml/pronunciation/smoke_clips`. Results and caveats:
[`docs/pronunciation-test-notes.md`](../../docs/pronunciation-test-notes.md).

## Known limitations

- **Intelligibility, not phonemes.** It can't say *which sound* was off.
- **Whisper autocorrects.** Accented speech is often transcribed as the intended words, so scores can
  beat a human listener's. Don't present the score as a diagnosis.
- **Uncalibrated.** Thresholds are placeholders until Hari's evaluation; keep `provisional: true`.
- The homophone list is small and hand-written; digits read as cardinals (`2026` → "two thousand
  twenty six"); hyphenated vs closed compounds ("post-traumatic") cost points.
- Single words are all-or-nothing: one wrong word scores 0, one right word 100.
