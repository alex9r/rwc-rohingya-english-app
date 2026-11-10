"""
Thin wrappers around the ML team's functions.

Each adapter imports the real function once at startup. If it isn't available
yet (not merged, or its dependencies aren't installed), it falls back to a stub
with the same response shape.
"""

import functools
import importlib
import importlib.util
import logging
import time
from typing import Any, BinaryIO, Callable

from app.observability import log_ml_request

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
# Luna: ml/pronunciation/scorer.py. It transcribes with Whisper internally, so like
# transcribe it is only "real" when faster-whisper is installed.
_score = (
    _import("ml.pronunciation", "score_pronunciation")
    if importlib.util.find_spec("faster_whisper")
    else None
)


def status() -> dict[str, str]:
    return {
        "transcribe": "real" if _transcribe else "stub", # stub = fallback values
        "translate": "real" if _translate else "stub",
        "pronunciation": "real" if _score else "stub",
    }


def _measured(service: str, status_of: Callable[[dict], str]):
    """Log one ml_request line (service, outcome, latency) per call, for CloudWatch."""

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            started = time.perf_counter()
            status = "exception"
            try:
                result = fn(*args, **kwargs)
                status = "stub" if result.get("stub") else status_of(result)
                return result
            except (ValueError, TypeError):
                status = "invalid_argument"
                raise
            finally:
                log_ml_request(service, status, (time.perf_counter() - started) * 1000)

        return inner

    return wrap


def warmup() -> None:
    """Load the Whisper model now so the first request isn't slow."""
    if _warmup:
        try:
            _warmup()
        except Exception:
            log.exception("Whisper warmup failed; first request will load the model")


@_measured("transcribe", lambda r: r["status"])
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


@_measured("translate", lambda r: r["status"])
def translate_text(text: str, direction: str) -> dict[str, Any]:
    """direction is "en->roh" or "roh->en". Returns {translation, status, confidence}."""
    if _translate is None:
        return {"translation": None, "status": "uncertain", "confidence": 0.0, "stub": True}
    return {**_translate(text, direction), "stub": False}


@_measured(
    "pronunciation",
    lambda r: r.get("status") or ("scored" if r.get("score") is not None else "unscored"),
)
def score_audio(audio: BinaryIO, target_text: str) -> dict[str, Any]:
    """Returns PronunciationResult.to_dict() (plus ``stub``). Never raises for bad audio."""
    if _score is None:
        return {
            "score": None,
            "status": "scoring_unavailable",
            "feedback": "Pronunciation scoring is not available yet.",
            "feedback_code": "stub",
            "stub": True,
        }
    result = _score(audio, target_text)
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    return {**result, "stub": False}
