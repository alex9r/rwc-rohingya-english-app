"""Speech module: Whisper transcription."""

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
    "Status",
    "TranscriptionResult",
    "classify_confidence",
    "supported_languages",
    "transcribe",
    "warmup",
]
