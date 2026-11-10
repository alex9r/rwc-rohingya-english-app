# Proposed API contract: `POST /api/pronunciation/score`

**Proposal, docs only**, for Nikiel to adopt or change. The scoring logic behind it is
[`ml/pronunciation`](../ml/pronunciation/README.md), built on [`ml/speech`](../ml/speech/README.md).

## Request

`multipart/form-data`

| Field | Required | Notes |
|---|---|---|
| `audio` | yes | Learner recording (the app records m4a). 0.3–60 s, 25 MB max, enforced by `transcribe()`. |
| `word_id` | yes | Lexicon id, e.g. `word_001`. **The backend looks up `target_text`**; the client never sends it. |
| `language` | no | Must be `"en"` (default). Learners practise spoken English; Whisper has no Rohingya. Anything else: `422`. |

**`reference_id` is dropped.** In `Rohingya_API_Spec_v3.docx` it appears as `"reference_001"` beside
`"word_id": "word_001"`, and reference audio is fetched per word, so it duplicates `word_id`. If it means
something else (say, one of several reference recordings), say so and it goes back in.

## Response (`200`)

```json
{
  "word_id": "word_001",
  "score": 75,
  "max_score": 100,
  "status": "scored",
  "transcript": "I need a dentist",
  "confidence": 0.86,
  "feedback": "Good try! Most of it was clear. Try the highlighted words again.",
  "feedback_code": "good",
  "needs_improvement": [{ "word": "doctor", "heard": "dentist", "issue": "different" }],
  "reference_audio_url": "https://…/word_001.mp3",
  "reference_audio_kind": "tts_placeholder",
  "score_basis": "asr_match",
  "provisional": true
}
```

| Field | Notes |
|---|---|
| `score` | int 0–100, `null` unless `status` is `scored` |
| `confidence` | ASR confidence 0–1, not pronunciation quality |
| `feedback` | short, plain English, encouraging |
| `feedback_code` | `great`, `good`, `keep_going`, `try_again`, `low_confidence`, `unclear_transcript`, `invalid_target`, or the pass-through status name |
| `needs_improvement` | `{word, heard, issue}`; `issue` is `missed`, `different`, `close` or `extra` (`word` null for `extra`, `heard` null for `missed`) |
| `reference_audio_url` / `_kind` | model pronunciation for the "hear it" button; kind is `tts_placeholder` or `native_speaker`; both `null` if none exists |
| `score_basis`, `provisional` | always `"asr_match"` and `true` for now |

`to_dict()` already returns everything except `word_id` and the two `reference_audio_*` fields,
which the endpoint adds from the lexicon/audio manifest.

### Statuses

| `status` | Meaning | `score` |
|---|---|---|
| `scored` | scored | 0–100 |
| `scoring_unavailable` | confidence too low, transcript unusable, or no target | `null` |
| `empty_audio`, `invalid_audio`, `too_short`, `too_long`, `no_speech` | passed through from `transcribe()`; the recording is the problem | `null` |
| `model_error` | passed through; the server is the problem | `null` |

Every non-`scored` response still carries a `feedback` message the app can show as is.

### Suggested HTTP codes (Nikiel's call)

`200` for every status (bad audio is a normal outcome; `503` for `model_error` is open); `404` unknown
`word_id`; `422` missing `audio`/`word_id` or `language` other than `"en"`.

### Implementation notes

- `transcribe()` is blocking and CPU-heavy: use a plain `def` handler, or `run_in_threadpool`.
- Call `ml.speech.warmup()` at startup.
- `score_pronunciation` never raises, so the handler only looks up the word and attaches the audio fields.

## Provisional scoring

The number is an uncalibrated ASR match: how well Whisper understood the learner, not which sounds were
right. Until evaluated with qualified speakers (Hari, then Welcome Centre review): no real numeric
feedback (grades, per-sound advice, rankings); `feedback` stays encouraging, never diagnostic; the app
shows the score as a rough guide with its "not validated" label.

## Differences from the spec's example

| Spec example | This proposal | Why |
|---|---|---|
| `"language": "rhg"` | `"en"` | The scorer judges English. |
| `needs_improvement: [{segment: "vowel_1", …}]` | `[{word, heard, issue}]` | An ASR match knows which *word* failed, not which sound. |
| "Practice the vowel sound." | encouraging, non-diagnostic text | Same reason. |
| no `provisional` / `score_basis` | both present | The spec itself says real numeric feedback should follow evaluation. |

## Mapping from the app's mock (`app/src/api/types.ts`)

`wordId` → `word_id`; `status` gains the pass-through statuses; `tips` → `needs_improvement`;
`validated: false` → `provisional: true` (inverse); new `reference_audio_url` / `_kind`.

## Open questions

1. **Nikiel:** does `reference_id` differ from `word_id`? `model_error`: `200` or `503`?
2. **Marcus / Nikiel:** where does reference audio live and what is the lexicon field called
   (`audio_url` in the README shape)? Placeholders are in `ml/tts` (PR #7).
3. **Hari:** do `MIN_CONFIDENCE` (0.5) and the score bands hold up once WER is measured?
