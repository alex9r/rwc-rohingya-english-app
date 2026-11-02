# Backend skeleton walkthrough

How the speech and pronunciation pieces connect, where each person's work plugs in, and
how to run what exists. It only describes what is in the repo on this branch; anything not
built yet is marked **pending**.

## What exists, what doesn't

| Piece | State |
|---|---|
| `app/` Expo app with a **mock** API client (`app/src/api/client.ts`) | exists |
| `ml/speech`: `transcribe()` (Mohammed, PR #4) | exists on `speech/transcribe-hardening`, not merged to `main` yet; this branch is built on top of it |
| `ml/pronunciation`: `score_pronunciation()` (this PR) | exists |
| FastAPI service (`backend/`): `/transcribe`, `/api/pronunciation/score` | **pending** (Nikiel). The folder is not in the repo yet. |
| `data/lexicon.json` | **pending**. Not in the repo yet; the README describes its planned shape. The app's `mockData.ts` stands in for it. |
| Reference audio for words (TTS placeholder or native speaker) | **pending, separate task** |
| WER evaluation and threshold calibration | **pending** (Hari) |

## How the pieces connect

```
 Expo app (app/)                      FastAPI backend (pending)                 ml/
 ───────────────                      ─────────────────────────                 ───
 record m4a  ──POST /transcribe────▶  ml.speech.transcribe(audio, lang)  ─────▶ faster-whisper
 (useRecorder)                              │
                                            ▼
 word practice ─POST /api/pronunciation/score ─▶ look up word_id in lexicon
 (word/[id].tsx)  audio + word_id + "en"        │  target_text = English side
                                                ▼
                                       ml.pronunciation.score_pronunciation(
                                           audio, target_text)
                                                │  calls ml.speech.transcribe(audio, "en")
                                                │  normalise → align → score
                                                ▼
                  ◀── JSON: score, feedback, needs_improvement, ──  + reference_audio_url
                       reference_audio_url, provisional:true            from lexicon/audio (pending)
```

1. **App → backend.** The app records m4a/AAC (`app/src/hooks/useRecorder.ts`) and today
   calls a mock (`api.translateSpeech`, `api.scorePronunciation`). "Swapping in the backend"
   means replacing those function bodies with `fetch()` calls; screens only call `api.*`.
2. **Backend → `ml/speech`.** `/transcribe` calls `transcribe(audio, language)`. It returns
   text, a 0–1 confidence and a status, and never raises on bad audio.
3. **Backend → `ml/pronunciation`.** `/api/pronunciation/score` looks up `word_id` in the
   lexicon to get the English target, then calls
   `score_pronunciation(audio, target_text)`. That function itself calls
   `transcribe(audio, language="en")` (English, because the learners are practising
   spoken English; Whisper has no Rohingya), then compares transcript and target.
4. **Lexicon / audio.** The endpoint adds `reference_audio_url` and
   `reference_audio_kind` from the lexicon entry. Until the audio exists these are `null`.

The scorer takes the transcriber as a parameter (`transcriber=`), so tests and any
future caching layer can swap it without touching the scoring code.

## Where each person's work plugs in

Roles I could verify from the task brief and the repo are filled in. **Nidhi and Linxi:
their areas were not stated, so those rows are left for the TPMs to fill in rather than
guessed.**

| Person | Work | Plugs in at |
|---|---|---|
| Mohammed | `ml/speech` `transcribe()` (PR #4) | Called by `/transcribe` and, inside `score_pronunciation`, with `language="en"`. Review the usage in `ml/pronunciation/scorer.py`. |
| Hari | WER evaluation, threshold calibration | Tunes `LOW_CONFIDENCE` / `MIN_CONFIDENCE` (0.5), `DEFAULT_FUZZY_THRESHOLD` (0.8) and the score bands (constants at the top of `scorer.py`). Decides when `provisional` can go. |
| Nikiel | FastAPI service | Builds `/transcribe` and `/api/pronunciation/score`; adopts or amends [the contract](pronunciation-api-contract.md); calls `warmup()` at startup. |
| Marcus | Words / lexicon content; TTS placeholder audio (later task) | Words he adds are the `word_id` → `target_text` source. Reference audio fills `reference_audio_url`. All data stays marked unvalidated until the Welcome Centre reviews it. |
| Nidhi | not stated | _TPMs to fill in_ |
| Linxi | not stated | _TPMs to fill in_ |
| Luna (speech) | `ml/pronunciation`, smoke test, these docs | this PR |

## How to run it

All commands from the repo root. Python 3.10 or newer (the code uses `X | None` types).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r ml/pronunciation/requirements.txt     # also installs ml/speech's requirements
```

**Tests (offline, no model download, safe for CI):**

```bash
python -m pytest ml -q          # ml/speech + ml/pronunciation
```

**Score one clip** (downloads the Whisper `small` model, about 460 MB, on first use):

```bash
python -m ml.pronunciation clip.m4a "I need a doctor"
python -m ml.speech clip.m4a --language en            # just the transcript
```

**Smoke test on public clips** (see [pronunciation-test-notes.md](pronunciation-test-notes.md)):

```bash
python -m ml.pronunciation.fetch_tatoeba_clips --out ml/pronunciation/smoke_clips
python -m ml.pronunciation.smoke_test ml/pronunciation/smoke_clips --out results.csv
```

**The app** (mock data, no backend needed):

```bash
cd app && npm install && npx expo start
```

**The backend:** nothing to run yet. When Nikiel's service lands, run it with the same
virtual environment so it can `import ml.speech` and `import ml.pronunciation` from the repo
root.

## The proposed API contract

Full version, with field tables, statuses and open questions:
[`pronunciation-api-contract.md`](pronunciation-api-contract.md). In short:

- **Request** (multipart): `audio`, `word_id` (backend looks up the target text), `language: "en"`.
- **Response:** `word_id`, `score`, `max_score`, `status`, `transcript`, `confidence`,
  `feedback`, `feedback_code`, `needs_improvement[{word, heard, issue}]`,
  `reference_audio_url`, `reference_audio_kind` (`tts_placeholder` | `native_speaker`),
  `score_basis: "asr_match"`, `provisional: true`.
- **Statuses:** `scored`, `scoring_unavailable`, and `transcribe()`'s own statuses
  (`empty_audio`, `invalid_audio`, `too_short`, `too_long`, `no_speech`, `model_error`).

## Related docs

- [`ml/pronunciation/README.md`](../ml/pronunciation/README.md): the scorer
- [`pronunciation-test-notes.md`](pronunciation-test-notes.md): smoke test on public audio
- [`pronunciation-recording-collection-plan.md`](pronunciation-recording-collection-plan.md): collecting Welcome Centre recordings
- [`pronunciation-feedback-idea.md`](pronunciation-feedback-idea.md): "was this score fair?" proposal
