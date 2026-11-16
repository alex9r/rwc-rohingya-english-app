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
            role TEXT NOT NULL,
            language TEXT NOT NULL CHECK (language IN ('en', 'rhg')),
            script TEXT NOT NULL DEFAULT 'latn',
            text TEXT NOT NULL,
            origin TEXT,
            verification TEXT,
            confidence NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1)
        )
        """,
        # Kept as a named constraint so new roles can be added to existing databases.
        "ALTER TABLE vocabulary_translations "
        "DROP CONSTRAINT IF EXISTS vocabulary_translations_role_check",
        "ALTER TABLE vocabulary_translations ADD CONSTRAINT vocabulary_translations_role_check "
        "CHECK (role IN ('headword', 'example', 'reference', 'variant', 'alternative'))",
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
        # Scored outputs from the translation / pronunciation pipeline. Append-only: a new
        # run adds a row, so we keep the history instead of overwriting the last score.
        """
        CREATE TABLE IF NOT EXISTS confidence_results (
            id BIGSERIAL PRIMARY KEY,
            word_id TEXT NOT NULL REFERENCES vocabulary_words(id),
            kind TEXT NOT NULL CHECK (kind IN ('reference', 'translation', 'pronunciation')),
            direction TEXT CHECK (direction IN ('rhg-en', 'en-rhg')),
            model TEXT NOT NULL,
            model_version TEXT,
            -- NULL = the model produced no usable score. Never store 0 for "unknown".
            score NUMERIC(4,3) CHECK (score BETWEEN 0 AND 1),
            output_text TEXT,
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS confidence_results_word_idx "
        "ON confidence_results(word_id, created_at DESC)",
        # Reviewer corrections are proposals. They never overwrite vocabulary_words by
        # themselves, so the original and every proposed fix stay on record.
        """
        CREATE TABLE IF NOT EXISTS reviewer_corrections (
            id BIGSERIAL PRIMARY KEY,
            word_id TEXT NOT NULL REFERENCES vocabulary_words(id),
            field TEXT NOT NULL CHECK (field IN (
                'rohingya_text', 'english_text', 'example_rohingya', 'example_english',
                'audio', 'image', 'category', 'other')),
            previous_value TEXT,
            proposed_value TEXT,
            reason TEXT,
            -- Pseudonymous reviewer id (for example 'R003'); never a real name.
            reviewer_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('proposed', 'accepted', 'rejected')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_by TEXT,
            decided_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS reviewer_corrections_word_idx "
        "ON reviewer_corrections(word_id)",
        "CREATE INDEX IF NOT EXISTS reviewer_corrections_status_idx "
        "ON reviewer_corrections(status)",
        # One row per stored recording. speaker_id is a pseudonym; the key to a real
        # person is held only by the Welcome Centre.
        """
        CREATE TABLE IF NOT EXISTS recordings (
            id BIGSERIAL PRIMARY KEY,
            speaker_id TEXT NOT NULL,
            word_id TEXT,
            take INTEGER,
            storage_key TEXT NOT NULL UNIQUE,
            consent_version TEXT NOT NULL,
            consent_uses JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'unvalidated'
                CHECK (status IN ('unvalidated', 'reviewed', 'rejected')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS recordings_speaker_idx ON recordings(speaker_id)",
        # 'app' = learner-audio bucket (30-day expiry); 'research' = research-audio bucket
        # (consented Centre recordings kept for benchmarking and fine-tuning).
        "ALTER TABLE recordings ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'app' "
        "CHECK (purpose IN ('app', 'research'))",
        # Proof that a deletion happened, with no recording content or key names in it.
        """
        CREATE TABLE IF NOT EXISTS recording_deletions (
            id BIGSERIAL PRIMARY KEY,
            speaker_id TEXT NOT NULL,
            recordings_deleted INTEGER NOT NULL,
            requested_via TEXT,
            completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS vocabulary_words_category_idx "
        "ON vocabulary_words(category_id)",
        "CREATE INDEX IF NOT EXISTS vocabulary_words_english_idx "
        "ON vocabulary_words(english_text)",
    ):
        conn.execute(statement)
