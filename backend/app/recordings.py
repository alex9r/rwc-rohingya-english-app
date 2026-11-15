"""Store and delete learner/speaker recordings.

Deletion is a command for the data holder (the Welcome Centre or a named team member),
not a public API route: this API has no authentication, so an HTTP delete would let
anyone who guessed a speaker id remove data. Run it from the CLI::

    python -m app.recordings delete-speaker S007            # shows what would go
    python -m app.recordings delete-speaker S007 --yes      # deletes

Set RECORDINGS_BUCKET to the learner-audio bucket and RESEARCH_RECORDINGS_BUCKET to the
research-audio bucket (see docs/aws-architecture.md). Both are cleared for the speaker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Mapping, Protocol, Sequence

from app import db

_SPEAKER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Tick-boxes on the consent form (docs/pronunciation-recording-collection-plan.md).
CONSENT_USES = frozenset(
    {"scorer_evaluation", "reference_audio", "model_training", "keep_after_project"}
)
# A research recording needs at least one of these.
RESEARCH_USES = frozenset({"scorer_evaluation", "model_training"})
PURPOSES = ("app", "research")


class RecordingStore(Protocol):
    def delete(self, key: str) -> None:
        """Remove the object and every stored version of it. Must be safe to repeat."""


class S3RecordingStore:
    def __init__(self, bucket: str, client: Any = None) -> None:
        if client is None:
            import boto3  # lazy: only needed when talking to AWS

            client = boto3.client("s3")
        self.bucket = bucket
        self.client = client

    def delete(self, key: str) -> None:
        # A plain delete on a versioned bucket only adds a delete marker and leaves the
        # audio recoverable, so remove every version and marker explicitly.
        paginator = self.client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=key):
            objects = [
                {"Key": item["Key"], "VersionId": item["VersionId"]}
                for item in (*page.get("Versions", []), *page.get("DeleteMarkers", []))
                if item["Key"] == key
            ]
            if not objects:
                continue
            response = self.client.delete_objects(
                Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True}
            )
            if response.get("Errors"):
                raise RuntimeError(f"S3 did not delete every version of {key}")


def _check_speaker_id(speaker_id: str) -> str:
    if not _SPEAKER_ID.match(speaker_id):
        raise ValueError("speaker_id must be 1-64 letters, digits, '-' or '_'")
    return speaker_id


def register_recording(
    speaker_id: str,
    storage_key: str,
    consent_version: str,
    consent_uses: Sequence[str],
    word_id: str | None = None,
    take: int | None = None,
    purpose: str = "app",
) -> None:
    """Record a stored recording. Refuses anything without matching consent."""
    _check_speaker_id(speaker_id)
    if not consent_version:
        raise ValueError("consent_version is required before a recording is stored")
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}")
    unknown = set(consent_uses) - CONSENT_USES
    if unknown:
        raise ValueError(f"unknown consent uses: {sorted(unknown)}")
    if purpose == "research" and not RESEARCH_USES & set(consent_uses):
        raise ValueError("research recordings need scorer_evaluation or model_training consent")
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        conn.execute(
            "INSERT INTO recordings "
            "(speaker_id, word_id, take, storage_key, consent_version, consent_uses, purpose) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)",
            (
                speaker_id, word_id, take, storage_key, consent_version,
                json.dumps(list(consent_uses)), purpose,
            ),  # fmt: skip
        )


def training_recordings() -> list[tuple[str, str]]:
    """(speaker_id, storage_key) for research recordings whose consent allows training.

    Fine-tuning jobs must read their file list from here, not list the bucket: the bucket
    also holds evaluation-only recordings.
    """
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        return conn.execute(
            "SELECT speaker_id, storage_key FROM recordings "
            "WHERE purpose='research' AND consent_uses ? 'model_training' "
            "AND status <> 'rejected' ORDER BY id"
        ).fetchall()


def count_recordings(speaker_id: str) -> int:
    _check_speaker_id(speaker_id)
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        return conn.execute(
            "SELECT COUNT(*) FROM recordings WHERE speaker_id=%s", (speaker_id,)
        ).fetchone()[0]


def delete_speaker_recordings(
    speaker_id: str,
    store: RecordingStore | Mapping[str, RecordingStore],
    requested_via: str = "request",
) -> int:
    """Delete every recording for a speaker, from storage first and then the database.

    ``store`` is one store for every recording, or a mapping from purpose ('app',
    'research') to the store holding those recordings. If the speaker has recordings in
    a purpose with no store, nothing is deleted and ValueError is raised, so a request
    can't be half-done by leaving the research copies behind.

    Everything runs in one transaction. If the store fails part-way, the database rows
    are rolled back, so the request can simply be run again (object deletion is
    idempotent). A row in ``recording_deletions`` records that it happened, without any
    recording content or key names.
    """
    _check_speaker_id(speaker_id)
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        rows = conn.execute(
            "SELECT id, storage_key, purpose FROM recordings WHERE speaker_id=%s",
            (speaker_id,),
        ).fetchall()
        stores = store if isinstance(store, Mapping) else dict.fromkeys(PURPOSES, store)
        missing = {purpose for _, _, purpose in rows} - set(stores)
        if missing:
            raise ValueError(f"no store configured for {sorted(missing)} recordings")
        for recording_id, key, purpose in rows:
            stores[purpose].delete(key)
            conn.execute("DELETE FROM recordings WHERE id=%s", (recording_id,))
        conn.execute(
            "INSERT INTO recording_deletions (speaker_id, recordings_deleted, requested_via) "
            "VALUES (%s, %s, %s)",
            (speaker_id, len(rows), requested_via),
        )
    return len(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    delete = sub.add_parser("delete-speaker", help="delete all recordings for one speaker id")
    delete.add_argument("speaker_id")
    delete.add_argument("--yes", action="store_true", help="actually delete (default: preview)")
    delete.add_argument("--via", default="cli", help="how the request arrived, for the log")
    args = parser.parse_args(argv)

    count = count_recordings(args.speaker_id)
    if not args.yes:
        print(f"{count} recording(s) for {args.speaker_id}. Re-run with --yes to delete them.")
        return 0
    buckets = {
        "app": os.getenv("RECORDINGS_BUCKET"),
        "research": os.getenv("RESEARCH_RECORDINGS_BUCKET"),
    }
    stores = {purpose: S3RecordingStore(name) for purpose, name in buckets.items() if name}
    if not stores:
        parser.error("set RECORDINGS_BUCKET and/or RESEARCH_RECORDINGS_BUCKET")
    deleted = delete_speaker_recordings(args.speaker_id, stores, args.via)
    print(f"Deleted {deleted} recording(s) for {args.speaker_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
