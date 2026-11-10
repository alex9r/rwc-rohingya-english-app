"""Per-clip error analysis and aggregation.

Per clip we report word-level substitutions / deletions ("missing words") /
insertions, WER, CER, and a phrase-level verdict. Aggregates are micro-averaged
(total errors / total reference words), which is the standard WER definition,
and can be broken down by any manifest field (speaker, noise, pace, ...).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Optional

from .text import Op, align, detect_script, edit_distance, normalize

# Phrase-level verdicts
CORRECT = "correct"
MISSING = "missing_words"      # only deletions: words dropped, nothing wrong or extra
INCORRECT = "incorrect_words"  # only substitutions: right length, wrong words
EXTRA = "extra_words"          # only insertions
MIXED = "mixed_errors"
NO_OUTPUT = "no_output"        # ASR returned nothing usable (counts as all words missing)
SCRIPT_MISMATCH = "script_mismatch"  # reference and hypothesis in different scripts: not scored


@dataclass
class ClipScore:
    clip_id: str
    verdict: str
    ref_words: int = 0
    subs: int = 0
    dels: int = 0
    ins: int = 0
    cer_edits: int = 0
    ref_chars: int = 0
    missing: list[str] = field(default_factory=list)
    substitutions: list[tuple[str, str]] = field(default_factory=list)  # (reference, heard)
    insertions: list[str] = field(default_factory=list)
    ref_script: str = ""
    hyp_script: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def scored(self) -> bool:
        return self.verdict != SCRIPT_MISMATCH

    @property
    def errors(self) -> int:
        return self.subs + self.dels + self.ins

    @property
    def wer(self) -> Optional[float]:
        return self.errors / self.ref_words if self.scored and self.ref_words else None

    @property
    def cer(self) -> Optional[float]:
        return self.cer_edits / self.ref_chars if self.scored and self.ref_chars else None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["wer"], d["cer"] = self.wer, self.cer
        return d


def _verdict(subs: int, dels: int, ins: int, hyp_words: int) -> str:
    if hyp_words == 0:
        return NO_OUTPUT
    kinds = [k for k, v in ((INCORRECT, subs), (MISSING, dels), (EXTRA, ins)) if v]
    if not kinds:
        return CORRECT
    return kinds[0] if len(kinds) == 1 else MIXED


def score_clip(
    clip_id: str,
    reference: str,
    hypothesis: str,
    *,
    fold_marks: bool = False,
    check_script: bool = True,
    meta: Optional[dict[str, Any]] = None,
) -> ClipScore:
    """Compare one hypothesis against its verified reference."""
    ref, hyp = normalize(reference, fold_marks=fold_marks), normalize(hypothesis, fold_marks=fold_marks)
    rs, hs = detect_script(reference), detect_script(hypothesis)
    base = dict(clip_id=clip_id, ref_script=rs, hyp_script=hs, meta=meta or {})

    # An ASR proxy (e.g. Bengali model) can answer in a different script from the
    # reference. Word-matching across scripts is meaningless (WER ~100%), so flag it.
    if check_script and hyp and rs != "NONE" and hs != "NONE" and rs != hs:
        return ClipScore(verdict=SCRIPT_MISMATCH, ref_words=len(ref), **base)

    ops = align(ref, hyp)
    subs = [o for o in ops if o.kind == "sub"]
    dels = [o for o in ops if o.kind == "del"]
    ins = [o for o in ops if o.kind == "ins"]
    return ClipScore(
        verdict=_verdict(len(subs), len(dels), len(ins), len(hyp)),
        ref_words=len(ref),
        subs=len(subs), dels=len(dels), ins=len(ins),
        cer_edits=edit_distance(list(" ".join(ref)), list(" ".join(hyp))),
        ref_chars=len(" ".join(ref)),
        missing=[o.ref for o in dels],
        substitutions=[(o.ref, o.hyp) for o in subs],
        insertions=[o.hyp for o in ins],
        **base,
    )


def summarize(scores: Iterable[ClipScore]) -> dict[str, Any]:
    scores = list(scores)
    scored = [s for s in scores if s.scored]
    words = sum(s.ref_words for s in scored)
    chars = sum(s.ref_chars for s in scored)
    verdicts = Counter(s.verdict for s in scores)
    return {
        "clips": len(scores),
        "clips_scored": len(scored),
        "clips_script_mismatch": verdicts.get(SCRIPT_MISMATCH, 0),
        "ref_words": words,
        "substitutions": sum(s.subs for s in scored),
        "deletions": sum(s.dels for s in scored),
        "insertions": sum(s.ins for s in scored),
        "wer": (sum(s.errors for s in scored) / words) if words else None,
        "cer": (sum(s.cer_edits for s in scored) / chars) if chars else None,
        "phrase_accuracy": (verdicts.get(CORRECT, 0) / len(scored)) if scored else None,
        "verdicts": dict(verdicts),
        "most_missed_words": Counter(w for s in scored for w in s.missing).most_common(10),
        "most_common_substitutions": Counter(p for s in scored for p in s.substitutions).most_common(10),
    }


def breakdown(scores: Iterable[ClipScore], key: str | Callable[[ClipScore], str]) -> dict[str, dict[str, Any]]:
    """Summaries grouped by a ``meta`` field name (or any function of the score)."""
    get = key if callable(key) else (lambda s: str(s.meta.get(key, "unknown")))
    groups: dict[str, list[ClipScore]] = defaultdict(list)
    for s in scores:
        groups[get(s)].append(s)
    return {g: summarize(v) for g, v in sorted(groups.items())}
