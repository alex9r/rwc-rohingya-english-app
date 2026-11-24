# ml/embedscore: embedding-based pronunciation comparison (experimental)

Compares a learner's clip with a reference reading of the same text, using frame embeddings
from a self-supervised speech model (wav2vec 2.0 base, layer 8) and dynamic time warping.
It returns a raw distance (lower = closer), not a 0–100 score.

**Not used by the app and not validated.** There is no human-rated learner speech in the
repo, so nothing can say whether a smaller distance means better pronunciation. The ASR-match
scorer in [`ml/pronunciation`](../pronunciation/README.md) stays the scorer the app uses.
Results of the first comparison are in
[`docs/embedding-scorer-experiment.md`](../../docs/embedding-scorer-experiment.md).

## Use

```python
from ml.embedscore import compare

r = compare("learner.m4a", "reference.mp3")      # any audio ml.speech.transcribe accepts
r.status       # "ok" | "invalid_audio" | "model_error" (never raises)
r.distance     # DTW cosine distance, e.g. 0.18
r.provisional  # always True
```

Reference audio must be a reading of the same text. For words in the lexicon that could be the
placeholder TTS in `data/audio/`; a native-speaker recording would be better.

## Setup and tests

```bash
pip install -r ml/embedscore/requirements.txt    # torch, transformers (+ ml/speech's)
python -m pytest ml/embedscore -q                # 7 tests, no model download
```

The model (`facebook/wav2vec2-base`, Apache-2.0, ~360 MB) downloads from Hugging Face the
first time `compare()` runs without a custom embedder.

## How it works

1. Decode to 16 kHz mono (`ml.speech.transcribe.load_audio`), trim leading/trailing silence.
2. Hidden states of one transformer layer, one vector per 20 ms, averaged in pairs.
3. Subtract each clip's mean vector (reduces speaker and channel offset), unit-length frames.
4. DTW with cosine cost and symmetric steps, divided by path length, so speaking speed
   barely changes the distance.

## Comparison script

```bash
python -m ml.embedscore.experiment --out /tmp/embed_run     # macOS; needs the local smoke clips
```

Runs three checks on the 75 English smoke-test clips against the ASR-match scorer. Reference
audio is generated locally with macOS `say` and not committed.

## Limits

- Raw distance, no mapping to a score: nothing to calibrate it against.
- A reference voice and a learner differ in speaker, prosody and recording, all of which move
  the distance without being pronunciation errors.
- Layer, pooling and silence trimming are fixed defaults, not tuned.
- Rohingya-accented English is untested: no recordings exist.
