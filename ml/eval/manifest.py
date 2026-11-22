"""Evaluation manifest: one JSON object per line (JSONL).

Required fields
    clip_id      unique string
    audio        path to the clip, relative to the manifest file
    reference    the verified transcript
    language     "rhg" (Rohingya) or "en"
    speaker_id   pseudonymous ID like "spk_007": never a name, never contact details
    verified_by  who checked the transcript (role or pseudonymous ID); empty = unverified

Optional (used for breakdowns)
    source_id    e.g. the Tatoeba sentence ID the prompt came from
    noise        quiet | noisy        pace   slow | normal | fast
    device       free text            accent free text

Audio files and manifests that point at real speakers stay out of git.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED = ("clip_id", "audio", "reference", "language", "speaker_id")
LANGUAGES = {"rhg", "en"}
# Fields that would identify a person. Refuse rather than carry them around.
FORBIDDEN = {"name", "speaker_name", "email", "phone", "address"}


@dataclass
class Clip:
    clip_id: str
    audio: Path
    reference: str
    language: str
    speaker_id: str
    verified_by: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return bool(self.verified_by.strip())


class ManifestError(ValueError):
    pass


def load(path: str | Path, *, allow_unverified: bool = False, check_audio: bool = True) -> list[Clip]:
    """Load and validate a manifest. Raises ManifestError listing every problem."""
    path = Path(path)
    problems: list[str] = []
    clips: list[Clip] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"line {n}: not valid JSON ({e.msg})")
            continue
        missing = [k for k in REQUIRED if not str(row.get(k, "")).strip()]
        if missing:
            problems.append(f"line {n}: missing {', '.join(missing)}")
            continue
        if bad := FORBIDDEN & row.keys():
            problems.append(f"line {n}: personal-data field(s) not allowed: {', '.join(sorted(bad))}")
            continue
        cid = str(row["clip_id"])
        if cid in seen:
            problems.append(f"line {n}: duplicate clip_id {cid!r}")
            continue
        seen.add(cid)
        if row["language"] not in LANGUAGES:
            problems.append(f"line {n}: language must be one of {sorted(LANGUAGES)}")
            continue
        audio = (path.parent / row["audio"]).resolve()
        if check_audio and not audio.is_file():
            problems.append(f"line {n}: audio not found: {row['audio']}")
            continue
        clip = Clip(
            clip_id=cid, audio=audio, reference=row["reference"], language=row["language"],
            speaker_id=str(row["speaker_id"]), verified_by=str(row.get("verified_by", "")),
            meta={k: v for k, v in row.items() if k not in REQUIRED and k != "verified_by"},
        )
        if not clip.verified and not allow_unverified:
            problems.append(f"line {n}: {cid} has no verified_by (pass allow_unverified to include it)")
            continue
        clips.append(clip)
    if problems:
        raise ManifestError(f"{path.name}: {len(problems)} problem(s)\n  " + "\n  ".join(problems))
    if not clips:
        raise ManifestError(f"{path.name}: no clips")
    return clips
