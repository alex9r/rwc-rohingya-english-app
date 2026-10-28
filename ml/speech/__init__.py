"""Speech module: Whisper transcription."""

from .transcribe import (
    LOW_CONFIDENCE,
    Status,
    TranscriptionResult,
    supported_languages,
    transcribe,
    warmup,
)

__all__ = [
    "LOW_CONFIDENCE",
    "Status",
    "TranscriptionResult",
    "supported_languages",
    "transcribe",
    "warmup",
]
