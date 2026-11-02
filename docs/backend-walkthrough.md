# Backend skeleton walkthrough

How the speech and pronunciation pieces connect, who plugs in where, and how to run what exists.
Only what is in the repo is described; the rest is marked **pending**.

## State

| Piece | State |
|---|---|
| `app/` Expo app with a **mock** API client (`app/src/api/client.ts`) | exists |
| `ml/speech` `transcribe()` (Mohammad, PR #4) | PR open; this work builds on it |
| `ml/pronunciation` `score_pronunciation()` (PR #5) | exists |
| `ml/tts` English placeholder audio + `data/audio_manifest.json` (PR #7) | exists, separate PR |
| FastAPI service (`/transcribe`, `/api/pronunciation/score`) | **pending** (Nikiel); no `backend/` folder yet |
| `data/lexicon.json` | **pending** (Marcus); the app's `mockData.ts` and the greetings JSON stand in |
| Native-speaker reference audio | **pending** |
| WER evaluation, threshold calibration | **pending** (Hari) |

## How the pieces connect

```
Expo app                         FastAPI backend (pending)               ml/
────────                         ─────────────────────────               ───
record m4a ──POST /transcribe──▶ ml.speech.transcribe(audio, lang) ────▶ faster-whisper
word practice
 audio + word_id + "en"
   ──POST /api/pronunciation/score──▶ look up word_id → English target (lexicon)
                                      ml.pronunciation.score_pronunciation(audio, target)
                                        └─ transcribe(audio, "en") → normalise → align → score
   ◀── score, feedback, needs_improvement, provisional:true
       + reference_audio_url (from lexicon / audio manifest)
```

1. **App → backend.** The app records m4a (`useRecorder`) and currently calls mocks
   (`api.translateSpeech`, `api.scorePronunciation`). Going live means replacing those bodies with `fetch()`.
2. **Backend → `ml/speech`.** `/transcribe` returns text, 0–1 confidence and a status; bad audio never raises.
3. **Backend → `ml/pronunciation`.** It scores in **English** (`language="en"`): learners practise spoken
   English and Whisper has no Rohingya. The transcriber is a parameter, so tests and caching can swap it.
4. **Reference audio.** `reference_audio_url` and `reference_audio_kind` come from the lexicon / audio
   manifest; `null` until audio exists.

## Who plugs in where

Nidhi's role was not given to me, so that row is blank for the TPMs.

| Person | Work | Plugs in at |
|---|---|---|
| Mohammad | `ml/speech` | Called by `/transcribe` and inside the scorer; review its use in `scorer.py` |
| Hari | WER evaluation, calibration | Tunes `MIN_CONFIDENCE` (0.5), fuzzy threshold (0.8), score bands (constants in `scorer.py`); decides when `provisional` can go |
| Nikiel | FastAPI service | Builds both endpoints; adopts or amends the [contract](pronunciation-api-contract.md); calls `warmup()` at startup |
| Marcus | Lexicon content, audio naming | `word_id` → target text source; approves the `<word_id>_en_tts_placeholder.mp3` naming and `audio_url` field; later native recordings |
| Linxi | Word Detail screen | Plays `audio_url`; labels it a placeholder |
| Nidhi | not stated | _TPMs to fill in_ |
| Luna | `ml/pronunciation`, `ml/tts`, these docs | PRs #5 and #7 |

## Run it

From the repo root, Python 3.10+:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r ml/pronunciation/requirements.txt
python -m pytest ml -q                                          # offline, no model download
python -m ml.pronunciation clip.m4a "I need a doctor" --model base   # first run downloads the model
python -m ml.pronunciation.smoke_test ml/pronunciation/smoke_clips_cv --manifest ml/pronunciation/smoke_manifest_cv.csv --model base
cd app && npm install && npx expo start                          # mock data, no backend needed
```

The backend: nothing to run yet. When it lands, use the same venv so it can import `ml.*` from the repo root.

## API contract

Full version: [`pronunciation-api-contract.md`](pronunciation-api-contract.md). In short: request
`audio`, `word_id`, `language:"en"`; response `score`, `status`, `transcript`, `confidence`, `feedback`,
`feedback_code`, `needs_improvement`, `reference_audio_url/_kind`, `score_basis:"asr_match"`,
`provisional:true`; statuses `scored`, `scoring_unavailable` plus `transcribe()`'s own.

## Related

[`ml/pronunciation`](../ml/pronunciation/README.md) ·
[test notes](pronunciation-test-notes.md) ·
[collection plan](pronunciation-recording-collection-plan.md) ·
[feedback idea](pronunciation-feedback-idea.md)
