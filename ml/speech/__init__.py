"""Speech module: Whisper transcription (this package) and pronunciation scoring."""

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
