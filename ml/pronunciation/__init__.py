"""Pronunciation module: score a spoken English attempt against a target text."""

from .scorer import (
    DEFAULT_FUZZY_THRESHOLD,
    MIN_CONFIDENCE,
    PronunciationResult,
    normalize,
    score_pronunciation,
)

__all__ = [
    "DEFAULT_FUZZY_THRESHOLD",
    "MIN_CONFIDENCE",
    "PronunciationResult",
    "normalize",
    "score_pronunciation",
]
