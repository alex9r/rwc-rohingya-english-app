"""Keep low-confidence clips so a Rohingya speaker can check them.

When ``transcribe()`` isn't confident, the app asks the user to say it again (see
``Action``). The clip it wasn't sure about is the most useful one to learn from, so with
the speaker's consent it goes into a review queue. A Rohingya speaker listens and either
writes down what was actually said (``verify``) or rejects the clip. Checked clips export
as a manifest for Luna's evaluation (``python -m ml.eval``), whose WER per clip feeds
``calibrate.py`` and Hari's model comparison.

    from ml.speech import transcribe
    from ml.speech.review import ReviewQueue

    queue = ReviewQueue("speech_review")
    r = transcribe(audio_bytes, "bn", attempt=2)
    clip_id = queue.save(audio_bytes, r, speaker_id="S007", consent_version="v1",
                         consent_uses=["scorer_evaluation"], word_id="w_doctor")
    # clip_id is None when the clip didn't need review or consent doesn't cover it

This store is a folder of audio files with one JSON record each, for development and
field tests. The record's fields match the backend's ``recordings`` table
(``backend/app/recordings.py``): speaker_id, word_id, take, storage_key,
consent_version, consent_uses, purpose ("research") and status (unvalidated / reviewed /
rejected), and the consent rules are the same, so the backend can store the same record
in S3 and Postgres.

Command line, for the reviewer and the data holder::

    python -m ml.speech.review speech_review list
    python -m ml.speech.review speech_review verify <clip_id> "what was said" --reviewer R01
    python -m ml.speech.review speech_review reject <clip_id> --reviewer R01 --note "not Rohingya"
    python -m ml.speech.review speech_review export manifest.jsonl
    python -m ml.speech.review speech_review delete-speaker S007 [--yes]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .transcribe import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    MAX_BYTES,
    AudioInput,
    ConfidenceLevel,
    TranscriptionResult,
)

# Same values as backend/app/recordings.py, so a record from here is valid there.
_SPEAKER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CONSENT_USES = frozenset({"scorer_evaluation", "reference_audio", "model_training", "keep_after_project"})
RESEARCH_USES = frozenset({"scorer_evaluation", "model_training"})  # one is needed to keep a clip
STATUSES = ("unvalidated", "reviewed", "rejected")
SPOKEN_LANGUAGES = ("rhg", "en")  # what the user was speaking (ml.eval manifest languages)

_CLIP_ID = re.compile(r"^[0-9a-f]{32}$")
_EXT = re.compile(r"^[a-z0-9]{1,5}$")
KEY_PREFIX = "speech-review"


class ReviewError(ValueError):
    pass


def needs_review(result: TranscriptionResult) -> bool:
    """True for the clips the app asks to repeat because the text wasn't trusted.

    Only transcribed clips with low confidence. Failures (silence, too short, server
    errors) have nothing in them for a reviewer to check.
    """
    return result.ok and result.confidence_level == ConfidenceLevel.LOW


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_speaker_id(speaker_id: str) -> str:
    if not isinstance(speaker_id, str) or not _SPEAKER_ID.match(speaker_id):
        raise ReviewError("speaker_id must be a pseudonymous ID of 1-64 letters, digits, '-' or '_'")
    return speaker_id


def _read_audio(audio: AudioInput, ext: Optional[str]) -> tuple[bytes, str]:
    if isinstance(audio, (bytes, bytearray)):
        data = bytes(audio)
    elif isinstance(audio, (str, os.PathLike)):
        path = Path(audio)
        data = path.read_bytes()
        ext = ext or path.suffix.lstrip(".")
    elif hasattr(audio, "read"):
        if hasattr(audio, "seek"):
            audio.seek(0)  # transcribe() has already read it
        data = audio.read()
    else:
        raise TypeError(f"unsupported audio type: {type(audio).__name__}")
    ext = (ext or "m4a").lower().lstrip(".")  # the Expo app records m4a
    if not _EXT.match(ext):
        raise ReviewError(f"bad audio extension: {ext!r}")
    if not data:
        raise ReviewError("audio is empty")
    if len(data) > MAX_BYTES:
        raise ReviewError("audio is over the size limit")
    return data, ext


def _write_json(path: Path, record: dict[str, Any]) -> None:
    """Write atomically, so a crash never leaves a half-written record."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class ReviewQueue:
    """A folder of clips waiting for (or done with) a Rohingya speaker's check."""

    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------------ saving

    def save(
        self,
        audio: AudioInput,
        result: TranscriptionResult,
        *,
        speaker_id: str,
        consent_version: str,
        consent_uses: Iterable[str],
        word_id: Optional[str] = None,
        expected_text: Optional[str] = None,
        spoken_language: str = "rhg",
        model: Optional[str] = None,
        ext: Optional[str] = None,
        force: bool = False,
    ) -> Optional[str]:
        """Queue a clip for review and return its clip_id, or None if it isn't kept.

        Not kept (None, nothing written): the result didn't need review, or the consent
        doesn't cover research use (scorer_evaluation or model_training). ``force=True``
        keeps any transcribed clip, e.g. a medium-confidence one the user said was wrong.

        Raises ReviewError only for caller mistakes: a non-pseudonymous speaker_id, no
        consent_version, an unknown consent use, or forcing a clip with no transcription.
        """
        _check_speaker_id(speaker_id)
        if not consent_version:
            raise ReviewError("consent_version is required before a recording is stored")
        uses = set(consent_uses)
        if unknown := uses - CONSENT_USES:
            raise ReviewError(f"unknown consent uses: {sorted(unknown)}")
        if spoken_language not in SPOKEN_LANGUAGES:
            raise ReviewError(f"spoken_language must be one of {SPOKEN_LANGUAGES}")
        if force and not result.ok:
            raise ReviewError(f"nothing to review: status is {result.status.value}")
        if not (force or needs_review(result)) or not uses & RESEARCH_USES:
            return None

        data, ext = _read_audio(audio, ext)
        clip_id = uuid.uuid4().hex
        level = result.confidence_level
        record = {
            # --- the backend's recordings row
            "clip_id": clip_id,
            "speaker_id": speaker_id,
            "word_id": word_id,
            "take": result.attempt,
            "storage_key": f"{KEY_PREFIX}/{clip_id}.{ext}",
            "consent_version": consent_version,
            "consent_uses": sorted(uses),
            "purpose": "research",
            "status": "unvalidated",
            "created_at": _now(),
            # --- what the app expected and what the model heard
            "spoken_language": spoken_language,
            "expected_text": expected_text,
            "asr": {
                "model": model,
                "language": result.language,  # the Whisper proxy, not "Rohingya"
                "text": result.text,
                "confidence": result.confidence,
                "confidence_level": level.value if level else None,
                "action": result.action.value,
                "reason": result.reason,
                "thresholds": {"high": HIGH_CONFIDENCE, "low": LOW_CONFIDENCE},
                "segments": [asdict(s) for s in result.segments],
            },
            # --- filled in by the reviewer
            "reference": None,
            "verified_by": None,
            "reviewed_at": None,
            "review_note": None,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{clip_id}.{ext}").write_bytes(data)
        _write_json(self._record_path(clip_id), record)
        return clip_id

    # ------------------------------------------------------------------ reading

    def _record_path(self, clip_id: str) -> Path:
        if not isinstance(clip_id, str) or not _CLIP_ID.match(clip_id):
            raise ReviewError(f"not a clip id: {clip_id!r}")
        return self.root / f"{clip_id}.json"

    def audio_path(self, clip_id: str) -> Path:
        return self.root / Path(self.get(clip_id)["storage_key"]).name

    def get(self, clip_id: str) -> dict[str, Any]:
        path = self._record_path(clip_id)
        if not path.is_file():
            raise ReviewError(f"no clip {clip_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def items(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise ReviewError(f"status must be one of {STATUSES}")
        if not self.root.is_dir():
            return []
        records = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*.json")
                   if _CLIP_ID.match(p.stem)]
        records = [r for r in records if status is None or r["status"] == status]
        return sorted(records, key=lambda r: r["created_at"])

    # ------------------------------------------------------------------ reviewing

    def _decide(self, clip_id: str, reviewer_id: str, **changes: Any) -> dict[str, Any]:
        if not reviewer_id or not reviewer_id.strip():
            raise ReviewError("reviewer_id is required")
        record = self.get(clip_id)
        if record["status"] != "unvalidated":
            raise ReviewError(f"clip {clip_id} is already {record['status']}")
        record.update(changes, verified_by=reviewer_id.strip(), reviewed_at=_now())
        _write_json(self._record_path(clip_id), record)
        return record

    def verify(self, clip_id: str, reference: str, reviewer_id: str, note: Optional[str] = None) -> dict[str, Any]:
        """The reviewer's transcript of what was actually said. A decision is final."""
        if not reference or not reference.strip():
            raise ReviewError("reference transcript is empty; use reject for an unusable clip")
        return self._decide(clip_id, reviewer_id, status="reviewed",
                            reference=reference.strip(), review_note=note)

    def reject(self, clip_id: str, reviewer_id: str, note: Optional[str] = None) -> dict[str, Any]:
        """Unusable: can't be understood, wrong language, not speech. Kept out of exports."""
        return self._decide(clip_id, reviewer_id, status="rejected", review_note=note)

    # ------------------------------------------------------------------ out

    def export_manifest(self, path: str | os.PathLike) -> int:
        """Write reviewed clips as an ml.eval manifest (JSONL). Returns the row count.

        Audio paths are relative to the manifest, as ml.eval expects. Keep the manifest
        out of git: it points at real speakers' recordings.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        base = path.parent.resolve()
        rows = []
        for r in self.items("reviewed"):
            audio = os.path.relpath((self.root / Path(r["storage_key"]).name).resolve(), base)
            row = {
                "clip_id": r["clip_id"],
                "audio": audio,
                "reference": r["reference"],
                "language": r["spoken_language"],
                "speaker_id": r["speaker_id"],
                "verified_by": r["verified_by"],
                "source": "app_low_confidence",
                "take": r["take"],
            }
            if r.get("word_id"):
                row["word_id"] = r["word_id"]
            rows.append(json.dumps(row, ensure_ascii=False))
        path.write_text("".join(line + "\n" for line in rows), encoding="utf-8")
        return len(rows)

    def delete_speaker(self, speaker_id: str) -> int:
        """Delete every clip and record for one speaker (a deletion request). Returns the count.

        A line in deletions.log records that it happened, with no content or clip ids.
        """
        _check_speaker_id(speaker_id)
        doomed = [r for r in self.items() if r["speaker_id"] == speaker_id]
        for r in doomed:
            (self.root / Path(r["storage_key"]).name).unlink(missing_ok=True)
            self._record_path(r["clip_id"]).unlink(missing_ok=True)
        if self.root.is_dir():
            with (self.root / "deletions.log").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"speaker_id": speaker_id, "clips_deleted": len(doomed),
                                    "completed_at": _now()}) + "\n")
        return len(doomed)


# --------------------------------------------------------------------------- CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.speech.review",
                                 description="Review queue for low-confidence clips.")
    ap.add_argument("root", help="review queue folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="show queued clips")
    ls.add_argument("--status", choices=STATUSES, default="unvalidated")
    v = sub.add_parser("verify", help="record what was actually said")
    v.add_argument("clip_id")
    v.add_argument("reference")
    v.add_argument("--reviewer", required=True, help="pseudonymous reviewer ID")
    v.add_argument("--note")
    rj = sub.add_parser("reject", help="mark a clip unusable")
    rj.add_argument("clip_id")
    rj.add_argument("--reviewer", required=True)
    rj.add_argument("--note")
    ex = sub.add_parser("export", help="write reviewed clips as an ml.eval manifest")
    ex.add_argument("manifest")
    d = sub.add_parser("delete-speaker", help="delete every clip for one speaker")
    d.add_argument("speaker_id")
    d.add_argument("--yes", action="store_true", help="actually delete (default: preview)")
    args = ap.parse_args(argv)

    q = ReviewQueue(args.root)
    try:
        if args.cmd == "list":
            items = q.items(args.status)
            for r in items:
                asr = r["asr"]
                print(f"{r['clip_id']}  {r['speaker_id']:<8} take {r['take']}  "
                      f"conf {asr['confidence']:.2f}  expected {r['expected_text']!r}  "
                      f"heard {asr['text']!r}  audio {Path(r['storage_key']).name}")
            print(f"{len(items)} {args.status}")
        elif args.cmd == "verify":
            q.verify(args.clip_id, args.reference, args.reviewer, args.note)
            print(f"{args.clip_id} reviewed")
        elif args.cmd == "reject":
            q.reject(args.clip_id, args.reviewer, args.note)
            print(f"{args.clip_id} rejected")
        elif args.cmd == "export":
            print(f"wrote {q.export_manifest(args.manifest)} reviewed clips to {args.manifest}")
        elif args.cmd == "delete-speaker":
            if not args.yes:
                n = sum(r["speaker_id"] == _check_speaker_id(args.speaker_id) for r in q.items())
                print(f"{n} clip(s) for {args.speaker_id}. Re-run with --yes to delete them.")
            else:
                print(f"deleted {q.delete_speaker(args.speaker_id)} clip(s) for {args.speaker_id}")
    except ReviewError as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
