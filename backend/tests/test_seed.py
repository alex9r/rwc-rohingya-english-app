import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main, seed, vocabulary_db

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPOSITORY_ROOT / "ml" / "translation" / "data" / "rohingya_greetings_40.json"


class RecordingConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement, params=()):
        self.statements.append((statement, params))
        return self


def test_load_dataset_uses_existing_repo_asset_and_keeps_unicode():
    dataset, entries = seed.load_dataset(DATASET)
    assert dataset == "Rohingya Greetings Lexicon"
    assert len(entries) == 40
    assert entries[0]["rohingya_text"] == "sólam"
    assert entries[0]["validation_status"] == "dictionary_attested_pending_native_review"


def test_load_dataset_rejects_missing_entry_fields(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"entries": [{"id": "missing-word"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="english_meaning.word"):
        seed.load_dataset(invalid)


def test_seed_is_repeatable_and_preserves_full_json(monkeypatch):
    connection = RecordingConnection()
    monkeypatch.setattr(db, "_connect", lambda: connection)
    monkeypatch.setattr(db, "ensure_vocabulary_schema", lambda conn: None)

    assert seed.seed_datasets([DATASET]) == 40
    word_inserts = [
        (statement, params)
        for statement, params in connection.statements
        if "INSERT INTO vocabulary_words" in statement
    ]
    assert len(word_inserts) == 40
    statement, params = word_inserts[0]
    assert "ON CONFLICT (dataset, source_id) DO UPDATE" in statement
    assert params[2] == "greeting_001"
    assert params[5] == "Hello"
    stored_entry = json.loads(params[-1])
    assert stored_entry["rohingya_text"] == "sólam"
    assert (
        stored_entry["example_sentence"]["rohingya"]
        == "Salaam alaikum! Bala aso ne? (not verified)"
    )


def test_seeded_entries_are_served_through_existing_api(monkeypatch):
    monkeypatch.setattr(vocabulary_db, "categories", lambda: [
        {"id": "greetings", "name": "Greetings", "description": "", "word_count": 1}
    ])
    word = {
        "id": "greetings-dataset:greeting_001",
        "source_id": "greeting_001",
        "dataset": "Rohingya Greetings Lexicon",
        "category_id": "greetings",
        "category_name": "Greetings",
        "english_text": "Hello",
        "rohingya_text": "sólam",
        "image_url": None,
        "audio_url": None,
        "verification_status": "dictionary_attested_pending_native_review",
        "source_entry": {
            "english_meaning": {
                "word": "Hello",
                "definition": "A greeting used when meeting someone.",
                "explanation": "Beginner greetings vocabulary.",
            },
            "related_topic": "Greetings",
            "part_of_speech": "Interjection",
            "validation_status": "dictionary_attested_pending_native_review",
            "example_sentence": {
                "english": "Hello! How are you?",
                "rohingya": "Salaam alaikum! Bala aso ne? (not verified)",
                "translation_verification": "not_verified",
            },
            "alternative_spellings_scripts": {"latin": ["hélou"]},
            "different_forms": [],
            "source_reference": {"title": "Dictionary", "url": "https://example.test"},
        },
    }
    monkeypatch.setattr(vocabulary_db, "category_words", lambda category_id: [word])
    monkeypatch.setattr(vocabulary_db, "words", lambda **kwargs: [word])
    monkeypatch.setattr(vocabulary_db, "word_count", lambda **kwargs: 1)
    monkeypatch.setattr(
        vocabulary_db, "word", lambda word_id: word if word_id == word["id"] else None
    )

    with TestClient(main.app) as client:
        categories = client.get("/api/categories").json()["categories"]
        category_words = client.get("/api/categories/greetings/words").json()["words"]
        results = client.get("/api/words?q=Hello").json()["words"]
        detail = client.get(f"/api/words/{word['id']}").json()
        examples = client.get(f"/api/words/{word['id']}/examples").json()
        forms = client.get(f"/api/words/{word['id']}/forms").json()
        scripts = client.get(f"/api/words/{word['id']}/scripts").json()

    assert categories[0]["id"] == "greetings"
    assert category_words[0]["english"] == "Hello"
    assert results[0]["id"] == word["id"]
    assert detail["english"]["term"] == "Hello"
    assert detail["rohingya"]["text"] == "sólam"
    assert detail["rohingya"]["verified"] is False
    assert detail["examples"][0]["verified"] is False
    assert examples["examples"][0]["english"] == "Hello! How are you?"
    assert forms["examples"] == examples["examples"]
    assert scripts["preferred_script"] == "latn"
