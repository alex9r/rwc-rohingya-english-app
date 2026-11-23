"""Read seeded vocabulary rows from the backend's PostgreSQL database."""

from __future__ import annotations

import re

import psycopg

from app import db


def _query(sql: str, params: tuple = ()):
    """Run a read query, returning ``None`` when the optional tables are absent."""
    try:
        with db._connect() as conn:
            return conn.execute(sql, params).fetchall()
    except psycopg.Error:
        # Until the optional vocabulary dataset is seeded, keep serving mock data.
        return None


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def categories():
    rows = _query(
        "SELECT c.id, c.name, COUNT(w.id) AS word_count "
        "FROM vocabulary_categories c LEFT JOIN vocabulary_words w ON w.category_id=c.id "
        "GROUP BY c.id, c.name ORDER BY c.name"
    )
    if rows is None or not rows:
        return None
    return [{"id": row[0], "name": row[1], "description": "", "word_count": row[2]} for row in rows]


def category_words(category_id: str):
    exists = _query("SELECT 1 FROM vocabulary_categories WHERE id=%s", (category_id,))
    if exists is None or not exists:
        return None
    rows = _query(
        "SELECT w.id, w.source_id, w.dataset, w.category_id, c.name, w.english_text, "
        "w.rohingya_text, w.image_url, w.audio_url, w.verification_status, w.entry_json, "
        "w.entry_type, w.confidence, w.confidence_tier, w.needs_review "
        "FROM vocabulary_words w JOIN vocabulary_categories c ON c.id=w.category_id "
        "WHERE w.category_id=%s ORDER BY w.english_text",
        (category_id,),
    )
    return rows_to_words(rows or [])


def words(
    category_id: str | None = None,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    clauses = []
    params: list = []
    if category_id:
        clauses.append("w.category_id=%s")
        params.append(category_id)
    if query:
        clauses.append("(w.english_text ILIKE %s OR w.rohingya_text ILIKE %s)")
        params.extend((f"%{query}%", f"%{query}%"))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _query(
        "SELECT w.id, w.source_id, w.dataset, w.category_id, c.name, w.english_text, "
        "w.rohingya_text, w.image_url, w.audio_url, w.verification_status, w.entry_json, "
        "w.entry_type, w.confidence, w.confidence_tier, w.needs_review "
        "FROM vocabulary_words w JOIN vocabulary_categories c ON c.id=w.category_id"
        f"{where} ORDER BY w.english_text LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    if rows is None:
        return None
    return rows_to_words(rows)


def word(word_id: str):
    rows = _query(
        "SELECT w.id, w.source_id, w.dataset, w.category_id, c.name, w.english_text, "
        "w.rohingya_text, w.image_url, w.audio_url, w.verification_status, w.entry_json, "
        "w.entry_type, w.confidence, w.confidence_tier, w.needs_review "
        "FROM vocabulary_words w JOIN vocabulary_categories c ON c.id=w.category_id "
        "WHERE w.id=%s",
        (word_id,),
    )
    if rows is None or not rows:
        return None
    return rows_to_words(rows)[0]


def word_count(category_id: str | None = None, query: str | None = None):
    clauses = []
    params: list = []
    if category_id:
        clauses.append("category_id=%s")
        params.append(category_id)
    if query:
        clauses.append("(english_text ILIKE %s OR rohingya_text ILIKE %s)")
        params.extend((f"%{query}%", f"%{query}%"))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _query(f"SELECT COUNT(*) FROM vocabulary_words{where}", tuple(params))
    if rows is None:
        return None
    return rows[0][0]


def rows_to_words(rows):
    return [
        {
            "id": row[0],
            "source_id": row[1],
            "dataset": row[2],
            "category_id": row[3],
            "category_name": row[4],
            "english_text": row[5],
            "rohingya_text": row[6],
            "image_url": row[7],
            "audio_url": row[8],
            "verification_status": row[9],
            "source_entry": row[10],
            "entry_type": row[11],
            "confidence": float(row[12]) if row[12] is not None else None,
            "confidence_tier": row[13],
            "needs_review": row[14],
        }
        for row in rows
    ]