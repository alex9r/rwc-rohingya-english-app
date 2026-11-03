"""
Thin wrappers around the ML team's functions.

Each adapter imports the real function once at startup. If it isn't available
yet (not merged, or its dependencies aren't installed), it falls back to a stub
with the same response shape.
"""

import importlib
import importlib.util
import logging
from typing import Any, BinaryIO

log = logging.getLogger(__name__)


def _import(module: str, name: str):
    try:
        return getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError) as exc:
        log.info("ML function %s.%s not available: %s", module, name, exc)
        return None


# ml/speech/transcribe.py
_transcribe = (
    _import("ml.speech", "transcribe") if importlib.util.find_spec("faster_whisper") else None
)
_warmup = _import("ml.speech", "warmup") if _transcribe else None
# Youssef: ml/translation/translate.py
_translate = _import("ml.translation", "translate")
# Luna: ml/speech (not sure if this was written as yet)
_score = _import("ml.speech", "score_pronunciation")


def status() -> dict[str, str]:
    return {
        "transcribe": "real" if _transcribe else "stub", # stub = fallback values
        "translate": "real" if _translate else "stub",
        "pronunciation": "real" if _score else "stub",
    }


def warmup() -> None:
    """Load the Whisper model now so the first request isn't slow."""
    if _warmup:
        try:
            _warmup()
        except Exception:
            log.exception("Whisper warmup failed; first request will load the model")


def transcribe_audio(audio: BinaryIO, language: str | None) -> dict[str, Any]:
    """Returns TranscriptionResult.to_dict() (plus ``stub``)."""
    if _transcribe is None:
        return {
            "status": "ok",
            "text": "Sample transcription (stub)",
            "confidence": 0.0,
            "is_confident": False,
            "language": language,
            "language_probability": None,
            "duration_s": None,
            "processing_s": 0.0,
            "segments": [],
            "error": None,
            "stub": True,
        }
    return {**_transcribe(audio, language).to_dict(), "stub": False}


def translate_text(text: str, direction: str) -> dict[str, Any]:
    """direction is "en->roh" or "roh->en". Returns {translation, status, confidence}."""
    if _translate is None:
        return {"translation": None, "status": "uncertain", "confidence": 0.0, "stub": True}
    return {**_translate(text, direction), "stub": False}


def score_audio(audio: BinaryIO, target_text: str) -> dict[str, Any]:
    """Returns {score 0-100, feedback, ...} from score_pronunciation(audio, target_text)."""
    if _score is None:
        return {
            "score": None,
            "feedback": "Pronunciation scoring is not available yet.",
            "stub": True,
        }
    return {**_score(audio, target_text), "stub": False}
