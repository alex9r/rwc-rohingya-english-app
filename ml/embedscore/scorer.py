"""Compare a learner clip with a reference clip of the same text. Never raises."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np

from ml.speech.transcribe import AudioInput, load_audio

from .dtw import dtw_distance
from .embed import DEFAULT_LAYER, Embedder, Wav2Vec2Embedder

OK = "ok"
INVALID_AUDIO = "invalid_audio"
MODEL_ERROR = "model_error"


@dataclass
class EmbeddingResult:
    status: str
    distance: Optional[float] = None     # DTW cosine distance; lower = closer to the reference
    learner_frames: int = 0
    reference_frames: int = 0
    layer: int = DEFAULT_LAYER
    provisional: bool = True             # no calibration, no human ratings behind it
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare(learner: AudioInput, reference: AudioInput, *, embedder: Optional[Embedder] = None,
            layer: int = DEFAULT_LAYER) -> EmbeddingResult:
    """DTW distance between the learner's speech and a reference reading of the same text.

    Deliberately returns a raw distance, not a 0-100 score: with no rated learner speech
    there is nothing to map distances onto.
    """
    embedder = embedder or Wav2Vec2Embedder()
    try:
        a, b = load_audio(learner), load_audio(reference)
    except Exception as e:  # unreadable or empty audio
        return EmbeddingResult(INVALID_AUDIO, layer=layer, error=str(e)[:200])
    try:
        ea, eb = embedder(np.asarray(a), [layer])[layer], embedder(np.asarray(b), [layer])[layer]
        return EmbeddingResult(OK, float(dtw_distance(ea, eb)), len(ea), len(eb), layer)
    except Exception as e:
        return EmbeddingResult(MODEL_ERROR, layer=layer, error=f"{type(e).__name__}: {str(e)[:160]}")
