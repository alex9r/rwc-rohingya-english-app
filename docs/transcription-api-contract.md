# Proposed API contract: asking again when transcription isn't sure

**Proposal, docs only.** For Nikiel (`POST /api/transcribe`), Linxi and Angelina (the
"please say that again" screens) and Nidhi (storing review clips). The logic is in
[`ml/speech`](../ml/speech/README.md); nothing here changes the backend or the app by itself.

Goal: users repeat only when they need to. `transcribe()` now says what to do next
(`action`) and why (`reason`), so the app doesn't have to interpret a confidence number.

## Request: `POST /api/transcribe` (`multipart/form-data`)

| Field | Required | Notes |
|---|---|---|
| `audio` | yes | the recording (the app records m4a); 0.3–60 s, 25 MB max |
| `language` | no | Whisper proxy code: `bn`, `ur`, `en`, or empty for auto-detect. See [Rohingya](#rohingya-rhg) below. |
| `attempt` | **new**, no (default 1) | which try this is **for the same phrase**: 1, 2, 3. The app counts; reset to 1 for a new phrase. The backend passes it as `transcribe(..., attempt=attempt)`. Without it every try counts as the first and the app never stops asking. |
| `word_id` | **new**, no | the phrase the user was asked to say, if any; stored with a review clip |
| `speaker_id`, `consent_version`, `consent_uses` | **new**, no | only needed to keep a review clip (below); same meaning as in `backend/app/recordings.py` |

## Response

Everything `TranscriptionResult.to_dict()` returns, as before, plus:

| Field | Values | Notes |
|---|---|---|
| `action` | `accept`, `confirm`, `ask_repeat`, `fallback`, `retry_later` | **what the app does next** (table below) |
| `reason` | `low_confidence`, `no_speech`, `too_short`, `too_long`, `empty_audio`, `invalid_audio`, or `null` | why the user is asked to record again; `null` when the text is usable or on a server error |
| `confidence_level` | `high`, `medium`, `low`, or `null` | `null` when nothing was transcribed |
| `attempt` | int | echoed back |

`is_confident` and `confidence` are unchanged, so current clients keep working.

### What the app does for each `action`

| `action` | When | Screen |
|---|---|---|
| `accept` | high confidence | use the text, move on |
| `confirm` | medium confidence | play back / show the text: "Did you say …?" **Yes** → use it. **No** → treat as `ask_repeat` and send the next try with `attempt + 1`. |
| `ask_repeat` | low confidence or unusable audio, before the last try | "Please say that again", with a hint from `reason` (below); next try with `attempt + 1` |
| `fallback` | still unusable on try 3 (`MAX_ATTEMPTS`) | stop asking: let the user pick from a list, tap the word, or skip. Never a fourth "say it again". |
| `retry_later` | `model_error` (server problem) | "Speech recognition is busy, please try again in a moment". Not the user's fault: don't count it as an attempt. |

Hints for `reason` (wording is the app's; keep them short and playable as audio):

| `reason` | Hint |
|---|---|
| `low_confidence` | say it a little slower, closer to the phone |
| `no_speech` | we didn't hear anything, check the microphone and speak after the beep |
| `too_short` | keep holding the button while you speak |
| `too_long` | just the word or the short sentence |
| `empty_audio`, `invalid_audio` | the recording didn't work, try again |

### HTTP status codes

Unchanged: `200` for `ok`, `422` for unusable audio, `503` for `model_error`, `400` for a bad
`language`. The `422` and `503` bodies carry `action` and `reason` too, so **the app should read
the body instead of mapping the status code to a fixed message**. (`app/src/api/transcription.ts`
currently turns every `422` into one generic "try again" and drops the reason.)

## Keeping clips for a Rohingya speaker to check

The clips the model wasn't sure about are the ones worth learning from. With the speaker's
consent the backend keeps them; a Rohingya speaker writes down what was actually said; checked
clips feed Luna's evaluation, which feeds the confidence thresholds.

```python
from ml.speech import ReviewQueue, needs_review, transcribe

result = transcribe(audio.file, language, attempt=attempt)
clip_id = review_queue.save(
    audio.file, result, speaker_id=speaker_id, consent_version=consent_version,
    consent_uses=consent_uses, word_id=word_id, expected_text=target_text,
)  # None when not kept
```

- **Kept**: `ok` results with low confidence (`needs_review(result)`), or a `confirm` the user said
  was wrong (`force=True`).
- **Not kept, no error**: confident clips, failed clips, and any clip whose consent doesn't
  include `scorer_evaluation` or `model_training`. The same rule as `register_recording(purpose="research")`.
- **Record fields** match the `recordings` table: `speaker_id`, `word_id`, `take` (= `attempt`),
  `storage_key` (`speech-review/<clip_id>.<ext>`), `consent_version`, `consent_uses`,
  `purpose` = `research`, `status` = `unvalidated` → `reviewed` / `rejected`. The record also
  holds what the model heard (`asr`: text, confidence, level, action, reason, proxy language,
  thresholds) and, after review, the `reference` transcript and `verified_by`.
- **Storage**: `ReviewQueue` is a folder store for development and field tests. In AWS the same
  record goes to the research bucket under `storage_key` plus `register_recording(...)`.
  **For Nidhi:** `confidence_results.kind` has no `transcription` value and needs a `word_id`;
  either add the kind or keep transcription confidence in the review record as it is now.
- **Deletion on request**: `ReviewQueue.delete_speaker(speaker_id)` or
  `python -m ml.speech.review <dir> delete-speaker S007 --yes`. In AWS, Nidhi's
  `python -m app.recordings delete-speaker` covers it once the clips are registered.
- **Reviewer workflow**: `python -m ml.speech.review <dir> list`, then `verify <clip_id> "<what was said>" --reviewer R01`
  or `reject <clip_id> --reviewer R01`. `export manifest.jsonl` writes the reviewed clips in
  Luna's `ml.eval` manifest format.

## Where the thresholds come from

`HIGH_CONFIDENCE` = 0.7 and `LOW_CONFIDENCE` = 0.5 are **provisional**. When Luna's Rohingya
test set has been run through `ml.eval`:

```bash
python -m ml.speech.calibrate --report eval_report.json --manifest manifest.jsonl --model <Hari's pick>
```

prints the recommended lines, and the deployment sets `RWC_HIGH_CONFIDENCE` / `RWC_LOW_CONFIDENCE`.
Thresholds belong to one model and proxy language, so re-run it if Hari's recommendation changes
either.

## Rohingya (`rhg`)

Whisper has no Rohingya, so `transcribe(language="rhg")` raises and the endpoint returns `400`.
The app's `transcribeRecording(uri, 'rhg')` therefore always fails today. Proposal: the
backend maps `rhg` to the proxy Hari recommends (`bn`, `ur`, or auto-detect) before calling
`transcribe()`, so the app keeps sending what the user actually speaks.
