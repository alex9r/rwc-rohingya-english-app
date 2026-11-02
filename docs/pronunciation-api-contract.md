# Proposed API contract: `POST /api/pronunciation/score`

**Status: proposal, docs only.** For Nikiel (backend) to adopt or change. Nothing in this
file is implemented as an endpoint; the scoring logic it wraps is
[`ml/pronunciation`](../ml/pronunciation/README.md) (this PR) on top of
[`ml/speech`](../ml/speech/README.md) (PR #4).

## Request

`multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `audio` | file | yes | The learner's recording. The Expo app records m4a/AAC. 0.3–60 s, 25 MB max (limits enforced by `transcribe()`). |
| `word_id` | string | yes | Lexicon id, e.g. `word_001`. **The backend looks up `target_text` itself** (the English side of the lexicon entry); the client never sends the target text. |
| `language` | string | no | Defaults to and must be `"en"`. Learners practise spoken English; Whisper has no Rohingya. Anything else is a `422`. |

**`reference_id` is dropped.** In the team's API spec (`Rohingya_API_Spec_v3.docx`, not
committed) the request example pairs `"word_id": "word_001"` with `"reference_id":
"reference_001"`, and reference audio is looked up per word (`GET /api/words/{word_id}/audio`).
That makes `reference_id` carry the same information as `word_id`. If it is meant to be
something different (for example one specific reference recording when a word has several),
say so and we add it back under that meaning.

## Response

`200 application/json`

```json
{
  "word_id": "word_001",
  "score": 75,
  "max_score": 100,
  "status": "scored",
  "transcript": "doctor",
  "confidence": 0.86,
  "feedback": "Good try! Most of it was clear. Try the highlighted words again.",
  "feedback_code": "good",
  "needs_improvement": [
    { "word": "doctor", "heard": "dentist", "issue": "different" }
  ],
  "reference_audio_url": "https://…/word_001.mp3",
  "reference_audio_kind": "tts_placeholder",
  "score_basis": "asr_match",
  "provisional": true
}
```

| Field | Type | Notes |
|---|---|---|
| `word_id` | string | echoed from the request |
| `score` | int 0–100 or `null` | `null` unless `status == "scored"` |
| `max_score` | int | always `100` |
| `status` | string | see below |
| `transcript` | string | what Whisper heard; may be empty |
| `confidence` | float 0–1 | ASR confidence, not pronunciation quality |
| `feedback` | string | short, plain English, encouraging |
| `feedback_code` | string | stable code the app can switch on: `great`, `good`, `keep_going`, `try_again`, `low_confidence`, `unclear_transcript`, `invalid_target`, or the pass-through status name |
| `needs_improvement` | list | `{word, heard, issue}`; `issue` ∈ `missed`, `different`, `close`, `extra`. `word` is `null` for `extra`; `heard` is `null` for `missed`. Empty when nothing to flag. |
| `reference_audio_url` | string or `null` | the model pronunciation for the app's "hear it" button. `null` if none exists yet. |
| `reference_audio_kind` | `"tts_placeholder"` or `"native_speaker"` or `null` | `null` when `reference_audio_url` is `null` |
| `score_basis` | string | always `"asr_match"` for now |
| `provisional` | bool | always `true` until the scoring is evaluated (below) |

`ml/pronunciation`'s `to_dict()` already produces everything except `word_id`,
`reference_audio_url` and `reference_audio_kind`, which the endpoint adds from the lexicon.
(`to_dict()` also returns `matched_words` and `missed_words`; the endpoint can pass them
through or drop them.)

### Statuses

| `status` | Meaning | `score` |
|---|---|---|
| `scored` | scored | 0–100 |
| `scoring_unavailable` | ASR confidence too low, transcript unusable, or no target text | `null` |
| `empty_audio`, `invalid_audio`, `too_short`, `too_long`, `no_speech` | passed through from `transcribe()`; the recording is the problem | `null` |
| `model_error` | passed through; the server is the problem | `null` |

Every non-`scored` response still has a `feedback` message the app can show as is.

### HTTP codes (suggestion, Nikiel's call)

- `200` for every status above, so the app handles one response shape. Bad audio is a
  normal outcome, not a request error. (Whether `model_error` should be a `503` instead
  is open.)
- `404` for an unknown `word_id`.
- `422` for a missing `audio` or `word_id`, or `language` other than `"en"`.

### Implementation notes for the endpoint

- `transcribe()` is blocking and CPU-heavy: use a plain `def` handler (FastAPI runs it in
  a threadpool) or `run_in_threadpool`, not a blocking call inside `async def`.
- Call `ml.speech.warmup()` at startup so the first request does not pay for model loading.
- `score_pronunciation` never raises, so the handler only needs to look up the word and
  attach the reference audio fields.

## Differences from the spec's illustrative example

The spec's `POST /api/pronunciation/score` example (`Rohingya_API_Spec_v3.docx`) differs from
this proposal in four ways, on purpose:

| Spec example | This proposal | Why |
|---|---|---|
| `"language": "rhg"` | `"language": "en"` | The scorer judges the learner's **English**. Whisper has no Rohingya, and there is no Rohingya TTS. |
| `needs_improvement: [{segment: "vowel_1", issue: "Vowel differs from reference"}]` | `[{word, heard, issue}]` | An ASR match can say which *word* was not recognised, not which *sound*. Segment- or vowel-level advice would be a made-up diagnosis. |
| `"feedback": "Good attempt. Practice the vowel sound."` | encouraging, non-diagnostic text | Same reason. |
| no `provisional` / `score_basis` | `provisional: true`, `score_basis: "asr_match"` | The spec itself says real numeric feedback should follow evaluation with qualified Rohingya speakers, and to return `scoring_unavailable` when the score cannot be trusted. |

## Provisional scoring: what the app may and may not say

`provisional: true` means the number comes from an uncalibrated ASR match
(`score_basis: "asr_match"`): it says how well Whisper understood the learner, not which
sounds were right or wrong. Until it has been evaluated with qualified speakers
(Hari's evaluation, then Welcome Centre review):

- Real numeric feedback (scores as grades, per-sound advice, progress rankings) should not
  be introduced.
- `feedback` stays encouraging, not diagnostic ("Try again slowly", never "your /th/ is
  wrong"). The messages in `ml/pronunciation` are written that way.
- The app should show the score as a rough guide and keep its "not validated" label.

## Mapping from the app's current mock

`app/src/api/types.ts` defines `PronunciationResult` for the mock client. Adopting this
contract means:

| App mock today | This contract |
|---|---|
| `wordId` | `word_id` |
| `status: 'scored' \| 'scoring_unavailable'` | plus the pass-through statuses above |
| `score: number \| null` | same |
| `feedback` | same, plus `feedback_code` |
| `tips: string[]` | replaced by `needs_improvement` |
| `validated: false` | replaced by `provisional: true` (inverse meaning) |
| no reference audio | `reference_audio_url`, `reference_audio_kind` |

## Open questions

1. **Nikiel:** is `reference_id` meant to differ from `word_id`? (See above.)
2. **Nikiel:** HTTP code for `model_error` (`200` vs `503`)?
3. **Marcus / Nikiel:** where does the reference audio live, and what does the lexicon call
   the field? (`audio_url` in the README's lexicon shape.) TTS placeholder audio is pending,
   a separate task; until it exists `reference_audio_url` is `null`.
4. **Hari:** whether `MIN_CONFIDENCE` (0.5) and the score bands hold up once WER is measured.
