"""Read the lexicon from DynamoDB (rwc-content, docs/aws-architecture.md).

Same functions and return shapes as ``vocabulary_db`` (Postgres), so main.py
doesn't care which store is behind it.

The whole lexicon (about 100 entries) is held in memory and re-scanned every
VOCAB_CACHE_TTL_S seconds; filtering, search and paging happen in Python. If
DynamoDB fails after a good load, the last copy keeps being served. If it has
never loaded, functions return None and the API falls back to mock data.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

TABLE = os.getenv("VOCAB_TABLE", "rwc-content")
CACHE_TTL_S = float(os.getenv("VOCAB_CACHE_TTL_S", "300"))
RETRY_AFTER_S = 30.0  # after a failed load, don't retry on every request

_lock = threading.Lock()
_cache: dict | None = None  # {"words": {id: word}, "categories": {id: category}}
_loaded_at = float("-inf")
_failed_at = float("-inf")
_clock = time.monotonic


def resource():
    import boto3
    from botocore.config import Config

    return boto3.resource(
        "dynamodb",
        region_name=os.getenv("AWS_REGION", "ca-central-1"),
        endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL") or None,
        # Fail fast: a slow DynamoDB shouldn't hold requests past the app's 4 s timeout.
        config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2}),
    )


def table():
    return resource().Table(TABLE)


def _scan() -> list[dict]:
    tbl = table()
    items, kwargs = [], {}
    while True:
        page = tbl.scan(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _word(item: dict) -> dict:
    """Same dict as vocabulary_db.rows_to_words produces for one row."""
    confidence = item.get("confidence")
    return {
        "id": item["id"],
        "source_id": item["source_id"],
        "dataset": item["dataset"],
        "category_id": item["category_id"],
        "category_name": item["category_name"],
        "english_text": item["english_text"],
        "rohingya_text": item.get("rohingya_text"),
        "image_url": item.get("image_url"),
        "audio_url": item.get("audio_url"),
        "verification_status": item.get("verification_status"),
        "source_entry": json.loads(item["entry_json"]),
        "entry_type": item.get("entry_type", "word"),
        # DynamoDB numbers come back as Decimal. Missing means "unscored", never 0.
        "confidence": float(confidence) if confidence is not None else None,
        "confidence_tier": item.get("confidence_tier"),
        "needs_review": bool(item.get("needs_review", True)),
    }


def _load() -> dict:
    words, categories = {}, {}
    for item in _scan():
        if item.get("sk") != "META":
            continue
        if item["pk"].startswith("ENTRY#"):
            words[item["id"]] = _word(item)
        elif item["pk"].startswith("CATEGORY#"):
            categories[item["id"]] = {
                "id": item["id"],
                "name": item["name"],
                "description": item.get("description", ""),
                "word_count": int(item.get("word_count", 0)),
            }
    return {"words": words, "categories": categories}


def _lexicon() -> dict | None:
    global _cache, _loaded_at, _failed_at
    if _cache is not None and _clock() - _loaded_at < CACHE_TTL_S:
        return _cache
    with _lock:
        now = _clock()
        if _cache is not None and now - _loaded_at < CACHE_TTL_S:
            return _cache
        if now - _failed_at < RETRY_AFTER_S:
            return _cache  # recently failed: serve stale (or None) without waiting again
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            _cache, _loaded_at = _load(), now
        except (BotoCoreError, ClientError) as exc:
            _failed_at = now
            log.warning(
                "DynamoDB lexicon load failed (%s); %s",
                type(exc).__name__,
                "serving the last good copy" if _cache else "falling back to mock data",
            )
        return _cache


def reset_cache() -> None:
    global _cache, _loaded_at, _failed_at
    with _lock:
        _cache, _loaded_at, _failed_at = None, float("-inf"), float("-inf")


def _sorted(words) -> list[dict]:
    return sorted(words, key=lambda w: (w["english_text"].casefold(), w["english_text"]))


def _filter(lexicon: dict, category_id: str | None, query: str | None) -> list[dict]:
    needle = query.casefold() if query else None
    return _sorted(
        w
        for w in lexicon["words"].values()
        if (not category_id or w["category_id"] == category_id)
        # Case-insensitive substring, like Postgres ILIKE (accents are not folded).
        and (
            needle is None
            or needle in w["english_text"].casefold()
            or needle in (w["rohingya_text"] or "").casefold()
        )
    )


# ----------------------------------------------- same API as vocabulary_db


def categories():
    lexicon = _lexicon()
    if not lexicon or not lexicon["categories"]:
        return None
    return sorted(lexicon["categories"].values(), key=lambda c: c["name"])


def category_words(category_id: str):
    lexicon = _lexicon()
    if not lexicon or category_id not in lexicon["categories"]:
        return None
    return _filter(lexicon, category_id, None)


def words(category_id: str | None = None, query: str | None = None, limit: int = 20,
          offset: int = 0):
    lexicon = _lexicon()
    if lexicon is None:
        return None
    return _filter(lexicon, category_id, query)[offset : offset + limit]


def word(word_id: str):
    lexicon = _lexicon()
    if lexicon is None:
        return None
    return lexicon["words"].get(word_id)


def word_count(category_id: str | None = None, query: str | None = None):
    lexicon = _lexicon()
    if lexicon is None:
        return None
    return len(_filter(lexicon, category_id, query))
