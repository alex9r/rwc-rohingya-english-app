"""Run a transcriber over a manifest and produce the error report."""

from __future__ import annotations

from typing import Any, Callable, Optional

from .manifest import Clip
from .metrics import NO_OUTPUT, ClipScore, breakdown, score_clip, summarize

# transcriber(path, language) -> (text, status). Injectable so tests need no model.
Transcriber = Callable[[str, Optional[str]], tuple[str, str]]


def whisper_transcriber(model_size: str = "small") -> Transcriber:
    """Adapter around ml.speech.transcribe (imported lazily: it pulls in the model stack)."""
    from ml.speech import transcribe

    def run(path: str, language: Optional[str]) -> tuple[str, str]:
        r = transcribe(path, language=language, model_size=model_size)
        return r.text, r.status.value

    return run


def evaluate(
    clips: list[Clip],
    transcriber: Transcriber,
    *,
    asr_language: Optional[str],
    fold_marks: bool = False,
    group_by: tuple[str, ...] = ("speaker_id", "noise", "pace"),
) -> dict[str, Any]:
    """Transcribe every clip and score it.

    ``asr_language`` is the Whisper code used as a proxy ("bn", "ur", "en", None for
    auto-detect). It is recorded in the report: a number without its proxy is meaningless.
    A clip the ASR returns nothing for is scored as all words missing (standard WER
    treatment) and its transcriber status is kept so failures stay visible.
    """
    scores: list[ClipScore] = []
    statuses: dict[str, str] = {}
    for clip in clips:
        text, status = transcriber(str(clip.audio), asr_language)
        statuses[clip.clip_id] = status
        meta = {"speaker_id": clip.speaker_id, "language": clip.language, **clip.meta}
        s = score_clip(clip.clip_id, clip.reference, text if status == "ok" else "",
                       fold_marks=fold_marks, meta=meta)
        scores.append(s)
    return {
        "asr_language": asr_language,
        "fold_marks": fold_marks,
        "overall": summarize(scores),
        "breakdown": {k: breakdown(scores, k) for k in group_by},
        "transcriber_failures": {c: st for c, st in statuses.items() if st != "ok"},
        "clips": [s.to_dict() for s in scores],
    }


def to_markdown(report: dict[str, Any]) -> str:
    def pct(x: Optional[float]) -> str:
        return "n/a" if x is None else f"{x * 100:.1f}%"

    o = report["overall"]
    lines = [
        f"# Transcription evaluation (ASR language proxy: `{report['asr_language']}`)",
        "",
        f"- clips: {o['clips']} ({o['clips_scored']} scored, {o['clips_script_mismatch']} script mismatch)",
        f"- WER {pct(o['wer'])} · CER {pct(o['cer'])} · exact-phrase accuracy {pct(o['phrase_accuracy'])}",
        f"- words: {o['ref_words']} reference · {o['substitutions']} wrong · {o['deletions']} missing · {o['insertions']} extra",
        f"- phrase verdicts: {o['verdicts']}",
    ]
    if o["clips_script_mismatch"]:
        lines.append("- **script mismatch**: the ASR answered in a different script from the reference; "
                     "those clips are not in WER. Fix the transcript script or add transliteration first.")
    if report["transcriber_failures"]:
        lines.append(f"- transcriber failures: {len(report['transcriber_failures'])}")
    for key, groups in report["breakdown"].items():
        lines += ["", f"## By {key}", "", "| group | clips | WER | CER | phrase acc |", "|---|---|---|---|---|"]
        for g, s in groups.items():
            lines.append(f"| {g} | {s['clips']} | {pct(s['wer'])} | {pct(s['cer'])} | {pct(s['phrase_accuracy'])} |")
    return "\n".join(lines) + "\n"
