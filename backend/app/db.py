"""Postgres connection helpers shared by health checks and vocabulary storage."""

import os

import psycopg


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER") or "rohingya",
        password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB") or "rohingya",
        connect_timeout=3,
    )


def ping() -> bool:
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def ensure_vocabulary_schema(conn: psycopg.Connection) -> None:
    """Create the small set of tables used by the JSON vocabulary seeder."""
    for statement in (
        """
        CREATE TABLE IF NOT EXISTS vocabulary_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vocabulary_words (
            id TEXT PRIMARY KEY,
            dataset TEXT NOT NULL,
            source_id TEXT NOT NULL,
            category_id TEXT NOT NULL REFERENCES vocabulary_categories(id),
            english_text TEXT NOT NULL,
            rohingya_text TEXT,
            image_url TEXT,
            audio_url TEXT,
            verification_status TEXT,
            entry_json JSONB NOT NULL,
            UNIQUE (dataset, source_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS vocabulary_words_category_idx "
        "ON vocabulary_words(category_id)",
        "CREATE INDEX IF NOT EXISTS vocabulary_words_english_idx "
        "ON vocabulary_words(english_text)",
    ):
        conn.execute(statement)
