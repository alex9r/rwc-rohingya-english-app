"""Text normalisation, script detection and word alignment for ASR evaluation.

No third-party dependencies. Everything here is language-agnostic except the
normalisation policy, which is built for the romanised Rohingya orthography used
in the Gamayun kit (apostrophes, ``*`` and hyphens carry meaning there).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

# Punctuation that never belongs to a word in the kit's orthography.
_STRIP = re.compile(r"[.,;:!?\"“”«»()\[\]{}…।۔،؟]")
_APOS = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})


def normalize(text: str, *, fold_marks: bool = False) -> list[str]:
    """Split ``text`` into comparable word tokens.

    Always: NFC, casefold, curly->straight apostrophes, strip sentence punctuation.
    Default keeps ``'`` ``*`` ``-`` inside tokens because the verified orthography
    uses them (``mon no'aish'shil``, ``aa*re``, ``Adam-e``).
    ``fold_marks=True`` is the lenient setting: drop ``'`` and ``*`` and split on
    ``-``, so spelling-mark variation between annotators doesn't count as an error.
    """
    t = unicodedata.normalize("NFC", text).translate(_APOS).casefold()
    t = _STRIP.sub(" ", t)
    if fold_marks:
        t = t.replace("'", "").replace("*", "").replace("-", " ")
    return [w for w in t.split() if w.strip("'*-")]


def detect_script(text: str) -> str:
    """Dominant Unicode script among letters: LATIN, BENGALI, ARABIC, ... or 'NONE'."""
    counts: dict[str, int] = {}
    for ch in text:
        if ch.isalpha():
            script = unicodedata.name(ch, "UNKNOWN").split(" ")[0]
            counts[script] = counts.get(script, 0) + 1
    return max(counts, key=counts.get) if counts else "NONE"


@dataclass(frozen=True)
class Op:
    """One alignment step. ``kind`` is equal | sub | del | ins."""

    kind: str
    ref: str | None
    hyp: str | None


def align(ref: Sequence[str], hyp: Sequence[str]) -> list[Op]:
    """Minimum-edit alignment (Levenshtein, unit costs) with a backtrace.

    Ties prefer equal > sub > del > ins so output is deterministic.
    """
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j - 1] + cost, d[i - 1][j] + 1, d[i][j - 1] + 1)
    ops: list[Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = ref[i - 1] == hyp[j - 1]
            if d[i][j] == d[i - 1][j - 1] + (0 if same else 1):
                ops.append(Op("equal" if same else "sub", ref[i - 1], hyp[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(Op("del", ref[i - 1], None))
            i -= 1
        else:
            ops.append(Op("ins", None, hyp[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    return sum(op.kind != "equal" for op in align(a, b))
