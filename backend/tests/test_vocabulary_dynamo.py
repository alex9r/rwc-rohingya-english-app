"""DynamoDB lexicon store, against moto's in-process DynamoDB (no AWS, no Docker)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from app import db, dynamo_load, main, seed, vocabulary, vocabulary_db, vocabulary_dynamo  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GREETINGS = REPOSITORY_ROOT / "ml" / "translation" / "data" / "rohingya_greetings_40.json"


@pytest.fixture
def dynamo(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_REGION", "ca-central-1")
    monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
    with moto.mock_aws():
        resource = boto3.resource("dynamodb", region_name="ca-central-1")
        table = dynamo_load.create_table(resource)
        vocabulary_dynamo.reset_cache()
        yield table
    vocabulary_dynamo.reset_cache()


@pytest.fixture
def client(dynamo, monkeypatch):
    dynamo_load.load([GREETINGS], dynamo)
    monkeypatch.setattr(vocabulary, "BACKEND", "dynamodb")
    monkeypatch.setattr(vocabulary, "store", vocabulary_dynamo)
    monkeypatch.setattr(db, "ping", lambda: False)  # no Postgres in this mode
    with TestClient(main.app) as c:
        yield c


def _entries(table):
    return [i for i in table.scan()["Items"] if i["pk"].startswith("ENTRY#")]


# ------------------------------------------------------------------ loader


def test_loader_writes_entries_and_categories(dynamo):
    assert dynamo_load.load([GREETINGS], dynamo) == 40
    items = dynamo.scan()["Items"]
    assert len(_entries(dynamo)) == 40
    categories = [i for i in items if i["pk"].startswith("CATEGORY#")]
    assert categories and sum(int(c["word_count"]) for c in categories) == 40


def test_loader_is_idempotent(dynamo):
    dynamo_load.load([GREETINGS], dynamo)
    dynamo_load.load([GREETINGS], dynamo)
    assert len(_entries(dynamo)) == 40


def test_loader_omits_missing_confidence():
    items = dynamo_load.build_items([GREETINGS])
    entries = [i for i in items if i["pk"].startswith("ENTRY#")]
    assert all("confidence" not in i or i["confidence"] is not None for i in entries)


# ---------------------------------------------------- parity with Postgres


def test_entries_match_what_postgres_would_return(dynamo):
    """Every entry equals the dict vocabulary_db.rows_to_words builds from a seeded row."""
    dynamo_load.load([GREETINGS], dynamo)
    dataset, entries = seed.load_dataset(GREETINGS)
    for entry in entries:
        v = seed._entry_values(dataset, entry)
        # Same column order as the SELECT in vocabulary_db.
        row = (v[0], v[2], v[1], v[3], v[4], v[5], v[6], v[7], v[8], v[9],
               json.loads(v[15]), v[10], v[12], v[13], v[14])
        expected = vocabulary_db.rows_to_words([row])[0]
        assert vocabulary_dynamo.word(v[0]) == expected


def test_unicode_survives(dynamo):
    dynamo_load.load([GREETINGS], dynamo)
    texts = {w["rohingya_text"] for w in vocabulary_dynamo.words(limit=100)}
    assert "sólam" in texts


# --------------------------------------------------------------- endpoints


def test_health_reports_dynamodb(client):
    body = client.get("/health").json()
    assert body["data_source"] == "dynamodb"
    assert body["database"] == "not_used"


def test_categories_come_from_dynamodb(client):
    categories = client.get("/api/categories").json()["categories"]
    assert sum(c["word_count"] for c in categories) == 40


def test_search_finds_entry(client):
    words = client.get("/api/words", params={"q": "sól"}).json()["words"]
    assert any(w["rohingya"] == "sólam" for w in words)


def test_search_is_case_insensitive_like_ilike(client):
    upper = client.get("/api/words", params={"q": "HELLO"}).json()["pagination"]["total"]
    lower = client.get("/api/words", params={"q": "hello"}).json()["pagination"]["total"]
    assert upper == lower > 0


def test_pagination(client):
    first = client.get("/api/words", params={"limit": 15}).json()
    assert first["pagination"]["total"] == 40
    assert len(first["words"]) == 15 and first["pagination"]["next_offset"] == 15
    last = client.get("/api/words", params={"limit": 15, "offset": 30}).json()
    assert len(last["words"]) == 10 and last["pagination"]["next_offset"] is None


def test_word_detail_and_404(client):
    word_id = client.get("/api/words", params={"limit": 1}).json()["words"][0]["id"]
    assert client.get(f"/api/words/{word_id}").json()["id"] == word_id
    assert client.get("/api/words/does-not-exist").status_code == 404


def test_category_words(client):
    category = client.get("/api/categories").json()["categories"][0]
    words = client.get(f"/api/categories/{category['id']}/words").json()["words"]
    assert len(words) == category["word_count"]


# ----------------------------------------------------------------- failure


def test_stale_cache_is_served_when_dynamodb_fails(client, dynamo, monkeypatch):
    assert client.get("/api/categories").status_code == 200  # warm the cache
    dynamo.delete()
    monkeypatch.setattr(vocabulary_dynamo, "CACHE_TTL_S", 0)  # force a reload attempt
    categories = client.get("/api/categories").json()["categories"]
    assert sum(c["word_count"] for c in categories) == 40  # still the DynamoDB data


def test_no_cache_and_dynamodb_down_falls_back_to_mock(dynamo, monkeypatch):
    dynamo.delete()
    monkeypatch.setattr(vocabulary, "BACKEND", "dynamodb")
    monkeypatch.setattr(vocabulary, "store", vocabulary_dynamo)
    with TestClient(main.app) as c:
        assert c.get("/health").json()["data_source"] == "mock"
        assert c.get("/api/categories").json()["categories"] == main.CATEGORIES


def test_cache_reloads_after_ttl(dynamo, monkeypatch):
    dynamo_load.load([GREETINGS], dynamo)
    now = [1000.0]
    monkeypatch.setattr(vocabulary_dynamo, "_clock", lambda: now[0])
    scans = []
    real_scan = vocabulary_dynamo._scan
    monkeypatch.setattr(vocabulary_dynamo, "_scan", lambda: scans.append(1) or real_scan())

    vocabulary_dynamo.categories()
    vocabulary_dynamo.categories()
    assert len(scans) == 1  # cached
    now[0] += vocabulary_dynamo.CACHE_TTL_S + 1
    vocabulary_dynamo.categories()
    assert len(scans) == 2  # expired, rescanned
