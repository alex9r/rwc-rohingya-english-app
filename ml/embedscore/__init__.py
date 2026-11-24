"""EXPERIMENTAL: embedding-based pronunciation comparison (learner audio vs reference audio).

Not used by the app and not validated: there is no human-rated learner speech to check it against.
See ml/embedscore/README.md.
"""

from .dtw import dtw_distance
from .scorer import EmbeddingResult, compare

__all__ = ["EmbeddingResult", "compare", "dtw_distance"]
