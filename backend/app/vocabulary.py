"""Which store serves the lexicon: Postgres locally, DynamoDB in AWS.

Set VOCAB_BACKEND=dynamodb to read rwc-content; anything else uses Postgres.
Every function returns None when its store has nothing, and main.py then
falls back to mock data.
"""

import os

from app import vocabulary_db

BACKEND = "dynamodb" if os.getenv("VOCAB_BACKEND", "").lower() == "dynamodb" else "postgres"

if BACKEND == "dynamodb":
    from app import vocabulary_dynamo as store
else:
    store = vocabulary_db


def categories():
    return store.categories()


def category_words(category_id: str):
    return store.category_words(category_id)


def words(category_id: str | None = None, query: str | None = None, limit: int = 20,
          offset: int = 0):
    return store.words(category_id=category_id, query=query, limit=limit, offset=offset)


def word(word_id: str):
    return store.word(word_id)


def word_count(category_id: str | None = None, query: str | None = None):
    return store.word_count(category_id=category_id, query=query)


def source() -> str:
    """For /health: which store is actually serving, or "mock" if neither has data."""
    return BACKEND if store.categories() is not None else "mock"
