"""Generate labelled English TTS placeholder audio for lexicon words.

Rules enforced here (not just documented):
* Only the ENGLISH side of an entry is voiced. Rohingya text is never read.
* Every file is named ``<word_id>_en_tts_placeholder.mp3`` and gets a manifest entry with
  ``kind: "tts_placeholder"`` and ``validated: false``.
* Existing files are never overwritten, and manifest entries of any other kind (for
  example ``native_speaker``) are carried over untouched.
* The lexicon file is only read.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from .backends import TTSBackend, to_mp3

KIND = "tts_placeholder"
SUFFIX = "_en_tts_placeholder.mp3"
LANGUAGE = "en"
MANIFEST_SCHEMA = "draft-1"
DEFAULT_LIMIT = 40

# The three words the app demos first. PLACEHOLDER CHOICE: the repo does not define the
# hero words; these are the greetings the app's mock data already shows (Hello,
# Thank you, Goodbye). The TPMs should confirm or replace.
HERO_IDS = ("greeting_001", "greeting_004", "greeting_002")

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class WordItem:
    word_id: str
    english: str


@dataclass
class GenerateReport:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # file already exists
    failed: list[tuple[str, str]] = field(default_factory=list)  # (word_id, reason)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"created {len(self.created)}, skipped {len(self.skipped)} (already exist), "
                f"failed {len(self.failed)}")


# --------------------------------------------------------------------------- lexicon


def load_words(lexicon_path: Path) -> list[WordItem]:
    """Read word ids and English text from a lexicon file. Never writes to it.

    Understands the draft shapes in the repo: ``entries[].english_meaning.word`` (the
    greetings/phrases files) and ``entries[].english`` (the README's lexicon shape).
    A list at the top level is also accepted.
    """
    data = json.loads(Path(lexicon_path).read_text(encoding="utf-8"))
    entries = data.get("entries", data.get("words", [])) if isinstance(data, dict) else data
    items = []
    for e in entries:
        word_id = e.get("id") or e.get("word_id")
        meaning = e.get("english_meaning")
        english = (meaning.get("word") if isinstance(meaning, dict) else None) or e.get("english")
        if word_id and isinstance(english, str) and english.strip():
            items.append(WordItem(str(word_id), english.strip()))
    return items


def select_words(
    items: Sequence[WordItem],
    ids: Optional[Sequence[str]] = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[WordItem], list[str]]:
    """Pick words by id (in the order given) or the first ``limit``. Returns (words, unknown ids)."""
    if ids is None:
        return list(items)[:limit], []
    by_id = {i.word_id: i for i in items}
    return [by_id[i] for i in ids if i in by_id], [i for i in ids if i not in by_id]


# --------------------------------------------------------------------------- manifest


def _load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": MANIFEST_SCHEMA,
        "notes": [
            "All audio listed as kind 'tts_placeholder' is machine-generated English speech, "
            "NOT a native-speaker recording, and is unvalidated.",
            "Native-speaker recordings, once reviewed by the Welcome Centre, are added as "
            "kind 'native_speaker' and replace the placeholder for the same word_id.",
        ],
        "entries": [],
    }


def _save_manifest(path: Path, manifest: dict) -> None:
    manifest["entries"].sort(key=lambda e: (e["word_id"], e["kind"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main


def generate(
    items: Sequence[WordItem],
    out_dir: Path,
    manifest_path: Path,
    backend: TTSBackend,
    *,
    repo_root: Optional[Path] = None,
    today: Optional[dt.date] = None,
) -> GenerateReport:
    """Create missing placeholder files and record them in the manifest. Idempotent.

    ``path`` in the manifest is relative to ``repo_root`` (default: the manifest's
    parent's parent, i.e. the repo root when the manifest is ``data/audio_manifest.json``).
    """
    out_dir, manifest_path = Path(out_dir), Path(manifest_path)
    root = Path(repo_root) if repo_root else manifest_path.resolve().parent.parent
    date = (today or dt.date.today()).isoformat()
    report = GenerateReport()
    manifest = _load_manifest(manifest_path)
    known = {(e["word_id"], e["kind"]) for e in manifest["entries"]}

    for item in items:
        if not _SAFE_ID.match(item.word_id):
            report.failed.append((item.word_id, "unsafe word id for a filename"))
            continue
        path = out_dir / f"{item.word_id}{SUFFIX}"
        if path.exists():
            report.skipped.append(item.word_id)
            if (item.word_id, KIND) not in known:
                report.warnings.append(
                    f"{path.name} exists but is not in the manifest; left as is "
                    "(delete it to regenerate and record it)"
                )
            continue
        try:
            samples, rate = backend.synthesize(item.english)
            audio = to_mp3(samples, rate)
        except Exception as e:  # one bad word must not stop the batch
            report.failed.append((item.word_id, f"{type(e).__name__}: {e}"))
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        manifest["entries"] = [e for e in manifest["entries"] if (e["word_id"], e["kind"]) != (item.word_id, KIND)]
        manifest["entries"].append({
            "word_id": item.word_id,
            "path": rel,
            "kind": KIND,
            "validated": False,
            "language": LANGUAGE,
            "text": item.english,
            "engine": backend.name,
            "voice": backend.voice,
            "license": backend.license_note,
            "date": date,
        })
        report.created.append(item.word_id)

    if report.created:
        _save_manifest(manifest_path, manifest)
    return report
