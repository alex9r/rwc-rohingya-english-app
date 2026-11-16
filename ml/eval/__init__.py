"""Transcription evaluation framework (word-level errors, missing words, phrase verdicts)."""

from .metrics import ClipScore, breakdown, score_clip, summarize
from .text import align, normalize

__all__ = ["ClipScore", "align", "breakdown", "normalize", "score_clip", "summarize"]
