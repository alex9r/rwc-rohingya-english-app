"""Store pipeline confidence results and reviewer corrections.

Corrections are proposals: accepting one records the decision but does not edit
``vocabulary_words``. Whoever applies it (and marks the entry verified) does that
deliberately, so a native-speaker review is never implied by a script.
"""

from __future__ import annotations

import json
from typing import Any

from app import db

SCORE_KINDS = ("reference", "translation", "pronunciation")
CORRECTION_FIELDS = (
    "rohingya_text", "english_text", "example_rohingya", "example_english",
    "audio", "image", "category", "other",
)  # fmt: skip


def add_confidence_result(
    word_id: str,
    kind: str,
    model: str,
    score: float | None,
    direction: str | None = None,
    model_version: str | None = None,
    output_text: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a scored result. ``score=None`` means the model gave no usable score."""
    if kind not in SCORE_KINDS:
        raise ValueError(f"kind must be one of {SCORE_KINDS}")
    if score is not None and not 0 <= score <= 1:
        raise ValueError("score must be between 0 and 1, or None")
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        conn.execute(
            "INSERT INTO confidence_results "
            "(word_id, kind, direction, model, model_version, score, output_text, details) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
            (word_id, kind, direction, model, model_version, score, output_text,
             json.dumps(details) if details is not None else None),
        )  # fmt: skip


def propose_correction(
    word_id: str,
    field: str,
    proposed_value: str,
    reviewer_id: str,
    reason: str | None = None,
) -> int:
    """Record a reviewer's suggested fix, keeping the value it was proposed against."""
    if field not in CORRECTION_FIELDS:
        raise ValueError(f"field must be one of {CORRECTION_FIELDS}")
    if not reviewer_id:
        raise ValueError("reviewer_id is required")
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        row = conn.execute(
            "SELECT english_text, rohingya_text FROM vocabulary_words WHERE id=%s", (word_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"Unknown word_id '{word_id}'")
        previous = {"english_text": row[0], "rohingya_text": row[1]}.get(field)
        return conn.execute(
            "INSERT INTO reviewer_corrections "
            "(word_id, field, previous_value, proposed_value, reason, reviewer_id) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (word_id, field, previous, proposed_value, reason, reviewer_id),
        ).fetchone()[0]


def decide_correction(correction_id: int, decision: str, decided_by: str) -> None:
    """Accept or reject a proposed correction. A decided correction cannot be changed."""
    if decision not in ("accepted", "rejected"):
        raise ValueError("decision must be 'accepted' or 'rejected'")
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        updated = conn.execute(
            "UPDATE reviewer_corrections SET status=%s, decided_by=%s, decided_at=now() "
            "WHERE id=%s AND status='proposed' RETURNING id",
            (decision, decided_by, correction_id),
        ).fetchone()
        if updated is None:
            raise LookupError(f"Correction {correction_id} not found or already decided")
