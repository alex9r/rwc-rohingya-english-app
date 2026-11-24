"""Dynamic time warping over frame embeddings. numpy only."""

from __future__ import annotations

import numpy as np


def _prepare(x: np.ndarray) -> np.ndarray:
    """Remove the utterance mean (reduces speaker and channel offset), then L2-normalise each frame."""
    x = np.asarray(x, dtype=np.float32)
    x = x - x.mean(axis=0, keepdims=True)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-8)


def dtw_distance(a: np.ndarray, b: np.ndarray, *, prepare: bool = True) -> float:
    """Length-normalised DTW distance between two [frames, dim] sequences, cosine local cost.

    0 means the frames line up exactly; larger is further apart. Symmetric steps, so the
    result is independent of argument order and of how fast either side was spoken.
    """
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[1]:
        raise ValueError("expected two [frames, dim] arrays with the same dim")
    if len(a) == 0 or len(b) == 0:
        raise ValueError("empty sequence")
    if prepare:
        a, b = _prepare(a), _prepare(b)
    cost = 1.0 - a @ b.T
    n, m = cost.shape
    inf = float("inf")
    prev = np.full(m + 1, inf)
    prev[0] = 0.0
    for i in range(n):
        c = cost[i]
        cur = [inf] * (m + 1)
        step = np.minimum(prev[:-1] + 2.0 * c, prev[1:] + c).tolist()   # diagonal, vertical
        cl = c.tolist()
        left = inf
        for j in range(m):
            left = min(step[j], left + cl[j])                           # horizontal
            cur[j + 1] = left
        prev = np.asarray(cur)
    return float(prev[m] / (n + m))
