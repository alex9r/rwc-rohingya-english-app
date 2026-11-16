"""Text-to-speech for English placeholder audio (see ml/tts/README.md)."""

from .backends import TTSBackend, available_backends, get_backend, register_backend
from .generate import GenerateReport, WordItem, generate, load_words, select_words

__all__ = [
    "GenerateReport",
    "TTSBackend",
    "WordItem",
    "available_backends",
    "generate",
    "get_backend",
    "load_words",
    "register_backend",
    "select_words",
]
