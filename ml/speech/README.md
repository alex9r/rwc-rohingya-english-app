# ml/speech — transcription

`transcribe()` turns one audio clip into text plus a confidence score using
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). It is built to sit
behind the backend's `/transcribe` endpoint: bad input never crashes it, it just
comes back with a status saying what went wrong.

Owner: Mohammed (speech).

## Setup

```bash
pip install -r ml/speech/requirements.txt
```

No system ffmpeg is needed; decoding uses PyAV, which faster-whisper already
installs. The model downloads from Hugging Face on first use (`small` is ~460 MB).

## Use

```python
from ml.speech import transcribe

r = transcribe("clip.m4a", language="bn", attempt=1)   # path, bytes, or a binary file object
r.status            # Status.OK
r.text              # "..."
r.confidence        # 0.0–1.0
r.confidence_level  # high / medium / low (None if nothing was transcribed)
r.action            # what the app does next: accept / confirm / ask_repeat / fallback / retry_later
r.reason            # why it asks again: "low_confidence", "no_speech", ... or None
r.is_confident      # True when ok and confidence >= LOW_CONFIDENCE
r.to_dict()         # JSON-ready dict for the API response
```

What the backend and app do with `action` and `reason`, and how review clips are kept:
[docs/transcription-api-contract.md](../../docs/transcription-api-contract.md).

From the command line:

```bash
python -m ml.speech clip.m4a --language bn --model small
```

## Input requirements

| | |
|---|---|
| Accepted types | file path, `bytes`, or binary file object (e.g. FastAPI `UploadFile.file`) |
| Formats | anything FFmpeg decodes: **m4a/AAC (what the Expo app records)**, wav, mp3, ogg/opus, webm, flac |
| Sample rate / channels | any; converted to 16 kHz mono internally |
| Length | 0.3 s to 60 s |
| Size | 25 MB max |
| `language` | a Whisper code used as a proxy for Rohingya (`"bn"`, `"ur"`, `"en"`) or `None` to auto-detect. Rohingya itself (`"rhg"`) is not a Whisper language and raises `ValueError`. Which proxy works best comes from Hari's evaluation. |

## Output

| Field | Type | Notes |
|---|---|---|
| `status` | string | see the table below |
| `text` | string | `""` unless status is `ok` |
| `confidence` | float 0–1 | `0.0` unless status is `ok` |
| `is_confident` | bool | `ok` and `confidence >= LOW_CONFIDENCE`; false means the text shouldn't be trusted |
| `confidence_level` | string or null | `high`, `medium`, `low`; null unless status is `ok` |
| `action` | string | `accept`, `confirm`, `ask_repeat`, `fallback`, `retry_later` (see below) |
| `reason` | string or null | `low_confidence` or the failure status; null when usable or on `model_error` |
| `attempt` | int | the `attempt` passed in |
| `language` | string or null | the language Whisper decoded as (the proxy, not "Rohingya") |
| `language_probability` | float or null | Whisper's language-ID probability |
| `duration_s` | float or null | clip length in seconds |
| `processing_s` | float | time spent in `transcribe()` |
| `segments` | list | `{start, end, text, confidence}` per Whisper segment |
| `error` | string or null | short, developer-facing reason when status isn't `ok` |

Example:

```json
{
  "status": "ok",
  "text": "I need a doctor",
  "confidence": 0.82,
  "is_confident": true,
  "language": "en",
  "language_probability": 0.97,
  "duration_s": 1.8,
  "processing_s": 0.61,
  "segments": [{"start": 0.0, "end": 1.6, "text": "I need a doctor", "confidence": 0.82}],
  "error": null
}
```

### Statuses

| `status` | Meaning |
|---|---|
| `ok` | transcribed (check `is_confident` before trusting the text) |
| `empty_audio` | zero bytes or zero samples |
| `invalid_audio` | missing file, not audio, or undecodable |
| `too_short` | under 0.3 s |
| `too_long` | over 60 s or 25 MB |
| `no_speech` | silent, or Whisper heard nothing |
| `model_error` | model failed to load or run (a server-side problem, not the user's audio) |

Silent clips are rejected before the model runs, which also stops Whisper's habit of
"hearing" phrases like *Thank you.* in silence.

## How confidence is computed

Per segment: `exp(avg_logprob)` (the average token probability) × `(1 − no_speech_prob)`,
halved if the compression ratio is above 2.4 (Whisper's sign of a repetition loop).
The clip score is the duration-weighted mean over segments.

This is a heuristic, not a calibrated probability, so the bands below are set from
measured word error rates rather than read as probabilities.

## When to ask again

| Level | Rule | `action` |
|---|---|---|
| high | `confidence >= HIGH_CONFIDENCE` (0.7) and no segment below `LOW_CONFIDENCE` | `accept` |
| medium | between the two, or high overall with one weak segment | `confirm` ("did you say …?") |
| low | `confidence < LOW_CONFIDENCE` (0.5) | `ask_repeat`, or `fallback` on attempt `MAX_ATTEMPTS` (3) |

Unusable audio also gets `ask_repeat` / `fallback`, with the status as `reason`;
`model_error` gets `retry_later` (the user did nothing wrong). The function keeps no
state: the caller passes `attempt` for each try at the same phrase.

### Calibrating the thresholds

0.7 and 0.5 are provisional. Once Luna's Rohingya clips have been through her
evaluation (`python -m ml.eval run ...`), use her report:

```bash
python -m ml.speech.calibrate --report eval_report.json --manifest manifest.jsonl --model small
# or a CSV with 'confidence' and 'wer' columns
python -m ml.speech.calibrate results_with_wer.csv
```

It transcribes each clip with the proxy language recorded in the report, pairs the
confidence with the clip's WER, and prints the lines plus how many clips fall in each
band. HIGH is set so accepted text averages at most 10% WER (`--accept-wer`); LOW so the
clips just under it average at least 50% WER (`--repeat-wer`). Set the result per
deployment with `RWC_HIGH_CONFIDENCE` / `RWC_LOW_CONFIDENCE`; re-run it when the model
or proxy language changes (Hari's recommendation).

## Keeping unsure clips for review

`ReviewQueue` keeps low-confidence clips, with research consent, so a Rohingya speaker
can write down what was really said. Reviewed clips export as an `ml.eval` manifest,
so they grow Luna's test set and the next calibration.

```python
from ml.speech import ReviewQueue

queue = ReviewQueue("speech_review")
clip_id = queue.save(audio, result, speaker_id="S007", consent_version="v1",
                     consent_uses=["scorer_evaluation"], word_id="w_doctor")  # None if not kept
```

```bash
python -m ml.speech.review speech_review list
python -m ml.speech.review speech_review verify <clip_id> "what was said" --reviewer R01
python -m ml.speech.review speech_review reject <clip_id> --reviewer R01 --note "not Rohingya"
python -m ml.speech.review speech_review export manifest.jsonl
python -m ml.speech.review speech_review delete-speaker S007 --yes
```

Records use the same fields and consent rules as the backend's `recordings` table, and
`speaker_id` must be pseudonymous. The queue folder holds real people's voices: keep it
out of git.

## Calling it from a server

What the backend needs to know about the function (the endpoint itself is the
backend's):

- `transcribe()` is blocking and CPU-heavy (about 1.5 s for a 2 s clip with `small`
  on an M2 CPU). Don't call it directly inside an `async` handler.
- The model loads on first use (about 1.5 s once downloaded). Call `warmup()` once at
  startup so the first request isn't slow.
- It takes a FastAPI `UploadFile.file` directly. The app records `.m4a`/AAC.
- It only raises for programmer errors: `ValueError` for an unsupported `language`
  code, `TypeError` for a wrong input type. Every audio problem comes back as a
  status, and `to_dict()` is the JSON body.
- `model_error` is the only status that means the server is at fault.

Settings via environment variables:

| Variable | Default | |
|---|---|---|
| `RWC_WHISPER_MODEL` | `small` | `tiny`/`base` for a weak dev server, `medium`/`large-v3` for accuracy |
| `RWC_WHISPER_DEVICE` | `auto` | `cpu` or `cuda` |
| `RWC_WHISPER_COMPUTE` | `int8` | `float16` on GPU |
| `RWC_HIGH_CONFIDENCE` | `0.7` | from `calibrate.py`; invalid values stop startup |
| `RWC_LOW_CONFIDENCE` | `0.5` | from `calibrate.py`; must not exceed the high line |

## Testing on dataset clips

```bash
# folder of clips
python -m ml.speech.run_clips path/to/clips --language bn --limit 30

# manifest CSV/TSV with a path column
python -m ml.speech.run_clips manifest.tsv --path-col path --out results.csv
```

Writes one CSV row per clip (status, text, confidence, timing) and prints a summary:
status counts, mean confidence, speed relative to real time.

## Tests

```bash
python -m pytest ml/speech -q
```

The tests use a fake model, so they run offline in under a second and are safe for CI.
They cover every failure status, m4a decoding (from a path and from bytes), stereo
44.1 kHz resampling, and the confidence maths.

## Known limitations

- Whisper has no Rohingya. Transcripts of Rohingya speech come out in the proxy
  language's script (Bengali script for `bn`) or as a loose romanisation, and
  confidence on them will be low. This is the honest baseline the README promises,
  not a bug.
- The thresholds aren't calibrated on Rohingya yet: there are no transcribed Rohingya
  clips until Luna's test set exists. The calibration path is ready (see above).
- Clips over 60 s are rejected rather than chunked; the app's clips are a word or a
  sentence.
