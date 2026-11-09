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
        # Structured columns promoted out of entry_json (added in place so existing
        # databases upgrade without a migration tool).
        "ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS entry_type TEXT "
        "NOT NULL DEFAULT 'word' CHECK (entry_type IN ('word', 'phrase'))",
        "ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS part_of_speech TEXT",
        # NULL confidence means "no scored reference translation", never "zero".
        "ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS confidence "
        "NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1)",
        "ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS confidence_tier TEXT",
        "ALTER TABLE vocabulary_words ADD COLUMN IF NOT EXISTS needs_review "
        "BOOLEAN NOT NULL DEFAULT TRUE",
        """
        CREATE TABLE IF NOT EXISTS vocabulary_translations (
            id BIGSERIAL PRIMARY KEY,
            word_id TEXT NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('headword', 'example', 'reference', 'variant')),
            language TEXT NOT NULL CHECK (language IN ('en', 'rhg')),
            script TEXT NOT NULL DEFAULT 'latn',
            text TEXT NOT NULL,
            origin TEXT,
            verification TEXT,
            confidence NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1)
        )
        """,
        "CREATE INDEX IF NOT EXISTS vocabulary_translations_word_idx "
        "ON vocabulary_translations(word_id)",
        """
        CREATE TABLE IF NOT EXISTS vocabulary_media (
            id BIGSERIAL PRIMARY KEY,
            word_id TEXT NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('image', 'audio')),
            -- Object key in the media bucket (or a legacy URL until assets are migrated).
            location TEXT NOT NULL,
            mime_type TEXT,
            verified BOOLEAN NOT NULL DEFAULT FALSE
        )
        """,
        "CREATE INDEX IF NOT EXISTS vocabulary_media_word_idx ON vocabulary_media(word_id)",
        """
        CREATE TABLE IF NOT EXISTS vocabulary_sources (
            id BIGSERIAL PRIMARY KEY,
            word_id TEXT NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            title TEXT,
            url TEXT,
            lookup_term TEXT,
            evidence TEXT,
            kind TEXT NOT NULL DEFAULT 'primary' CHECK (kind IN ('primary', 'checked'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS vocabulary_sources_word_idx ON vocabulary_sources(word_id)",
        "CREATE INDEX IF NOT EXISTS vocabulary_words_category_idx "
        "ON vocabulary_words(category_id)",
        "CREATE INDEX IF NOT EXISTS vocabulary_words_english_idx "
        "ON vocabulary_words(english_text)",
    ):
        conn.execute(statement)
