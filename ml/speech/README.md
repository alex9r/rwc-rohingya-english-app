# ml/speech — transcription

`transcribe()` turns one audio clip into text plus a confidence score using
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). It is built to sit
behind the backend's `/transcribe` endpoint: bad input never crashes it, it just
comes back with a status saying what went wrong.

Owner: Mohammed (speech). Pronunciation scoring (`score_pronunciation`) is Luna's
and will live alongside this.

## Setup

```bash
pip install -r ml/speech/requirements.txt
```

No system ffmpeg is needed; decoding uses PyAV, which faster-whisper already
installs. The model downloads from Hugging Face on first use (`small` is ~460 MB).

## Use

```python
from ml.speech import transcribe

r = transcribe("clip.m4a", language="bn")   # path, bytes, or a binary file object
r.status        # Status.OK
r.text          # "..."
r.confidence    # 0.0–1.0
r.is_confident  # True when ok and confidence >= 0.5
r.to_dict()     # JSON-ready dict for the API response
```

From the command line:

```bash
python -m ml.speech.transcribe clip.m4a --language bn --model small
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
| `is_confident` | bool | `ok` and `confidence >= 0.5`; when false the app should show its "not sure" state |
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

| `status` | Meaning | Suggested app message |
|---|---|---|
| `ok` | transcribed | show text (with "not sure" if `is_confident` is false) |
| `empty_audio` | zero bytes or zero samples | "We didn't get a recording. Try again." |
| `invalid_audio` | missing file, not audio, or undecodable | "Something went wrong with the recording. Try again." |
| `too_short` | under 0.3 s | "Hold the button a little longer." |
| `too_long` | over 60 s or 25 MB | "Try a shorter recording." |
| `no_speech` | silent, or Whisper heard nothing | "We couldn't hear you. Try again closer to the phone." |
| `model_error` | model failed to load or run | "Speech isn't available right now." (server-side problem) |

Silent clips are rejected before the model runs, which also stops Whisper's habit of
"hearing" phrases like *Thank you.* in silence.

## How confidence is computed

Per segment: `exp(avg_logprob)` (the average token probability) × `(1 − no_speech_prob)`,
halved if the compression ratio is above 2.4 (Whisper's sign of a repetition loop).
The clip score is the duration-weighted mean over segments.

This is a heuristic, not a calibrated probability. Once Hari's evaluation has clips
with reference transcripts, compare confidence against WER (`run_clips.py` writes
both) and adjust the 0.5 threshold.

## Wiring it into the backend (for Nikiel)

`transcribe()` is blocking and CPU-heavy, so use a plain `def` endpoint (FastAPI runs
it in a thread pool) and load the model at startup:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from ml.speech import Status, transcribe, warmup

@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup()  # load the model at startup so the first request isn't slow
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/transcribe")
def transcribe_endpoint(audio: UploadFile = File(...), language: str | None = None):
    try:
        result = transcribe(audio.file, language=language)
    except ValueError as e:  # unsupported language code
        return JSONResponse({"status": "invalid_request", "error": str(e)}, status_code=422)
    code = 503 if result.status == Status.MODEL_ERROR else 200
    return JSONResponse(result.to_dict(), status_code=code)
```

Audio problems return 200 with a status so the app handles one response shape;
only a server-side model failure is a 503. The app records with
`RecordingPresets.HIGH_QUALITY`, so expect `.m4a` uploads.

Settings via environment variables:

| Variable | Default | |
|---|---|---|
| `RWC_WHISPER_MODEL` | `small` | `tiny`/`base` for a weak dev server, `medium`/`large-v3` for accuracy |
| `RWC_WHISPER_DEVICE` | `auto` | `cpu` or `cuda` |
| `RWC_WHISPER_COMPUTE` | `int8` | `float16` on GPU |

## Testing on dataset clips

```bash
# folder of clips (reference text optional, in clip.txt next to clip.wav)
python -m ml.speech.run_clips path/to/clips --language bn --limit 50

# manifest CSV/TSV with path and transcript columns
python -m ml.speech.run_clips manifest.tsv --path-col path --ref-col sentence --out results_bn.csv
```

Writes one CSV row per clip (status, text, confidence, timing, and WER/CER when a
reference is given) and prints a summary: status counts, mean confidence, speed
relative to real time.

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
- Confidence isn't calibrated yet (see above).
- Clips over 60 s are rejected rather than chunked; the app's clips are a word or a
  sentence.
