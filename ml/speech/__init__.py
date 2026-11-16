"""Speech module: Whisper transcription, and a review queue for clips it wasn't sure about."""

from .transcribe import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    MAX_ATTEMPTS,
    Action,
    ConfidenceLevel,
    Status,
    TranscriptionResult,
    classify_confidence,
    supported_languages,
    transcribe,
    warmup,
)

__all__ = [
    "HIGH_CONFIDENCE",
    "LOW_CONFIDENCE",
    "MAX_ATTEMPTS",
    "Action",
    "ConfidenceLevel",
    "ReviewQueue",
    "Status",
    "TranscriptionResult",
    "classify_confidence",
    "needs_review",
    "supported_languages",
    "transcribe",
    "warmup",
]


def __getattr__(name):
    # Loaded on first use, so `python -m ml.speech.review` doesn't import itself twice.
    if name in ("ReviewQueue", "needs_review"):
        from . import review

        return getattr(review, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
