"""Frame embeddings from a self-supervised speech model (wav2vec 2.0 base by default)."""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np

MODEL_ID = "facebook/wav2vec2-base"   # Apache-2.0, not fine-tuned
DEFAULT_LAYER = 8                     # middle layers carry the most phonetic content
SAMPLE_RATE = 16000
MAX_SECONDS = 30.0


class Embedder(Protocol):
    def __call__(self, samples: np.ndarray, layers: Sequence[int]) -> dict[int, np.ndarray]: ...


def trim_silence(samples: np.ndarray, rel_db: float = -35.0, frame: int = 320) -> np.ndarray:
    """Cut leading and trailing frames quieter than ``rel_db`` below the loudest frame."""
    n = len(samples) // frame
    if n == 0:
        return samples
    rms = np.sqrt((samples[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
    if rms.max() <= 0:
        return samples
    keep = np.flatnonzero(rms >= rms.max() * 10 ** (rel_db / 20))
    return samples[keep[0] * frame : (keep[-1] + 1) * frame]


def pool(x: np.ndarray, k: int = 2) -> np.ndarray:
    """Average every ``k`` frames (20 ms -> 40 ms at k=2); keeps DTW fast."""
    n = (len(x) // k) * k
    return x[:n].reshape(-1, k, x.shape[1]).mean(axis=1) if n else x


class Wav2Vec2Embedder:
    """Loads the model on first call. Needs torch and transformers (see requirements.txt)."""

    def __init__(self, model_id: str = MODEL_ID):
        self.model_id, self._model, self._fe = model_id, None, None

    def _load(self):
        import torch
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2Model

        self._torch = torch
        self._fe = Wav2Vec2FeatureExtractor.from_pretrained(self.model_id)
        self._model = Wav2Vec2Model.from_pretrained(self.model_id).eval()

    def __call__(self, samples: np.ndarray, layers: Sequence[int]) -> dict[int, np.ndarray]:
        if self._model is None:
            self._load()
        samples = trim_silence(samples[: int(MAX_SECONDS * SAMPLE_RATE)])
        inputs = self._fe(samples, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with self._torch.no_grad():
            out = self._model(**inputs, output_hidden_states=True)
        return {l: pool(out.hidden_states[l][0].numpy()) for l in layers}
