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

r = transcribe("clip.m4a", language="bn")   # path, bytes, or a binary file object
r.status        # Status.OK
r.text          # "..."
r.confidence    # 0.0–1.0
r.is_confident  # True when ok and confidence >= 0.5
r.to_dict()     # JSON-ready dict for the API response
```

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
| `is_confident` | bool | `ok` and `confidence >= 0.5`; false means the text shouldn't be trusted |
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

This is a heuristic, not a calibrated probability. Once Hari's evaluation has WER per
clip, compare it against the confidence from `run_clips.py` and adjust the 0.5
threshold.

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
- Confidence isn't calibrated yet (see above).
- Clips over 60 s are rejected rather than chunked; the app's clips are a word or a
  sentence.
