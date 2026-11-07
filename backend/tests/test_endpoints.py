import pytest
from fastapi.testclient import TestClient

from app import db, main, ml_adapters, vocabulary_db


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: True)  # no Postgres in tests
    monkeypatch.setattr(vocabulary_db, "categories", lambda: None)
    monkeypatch.setattr(vocabulary_db, "category_words", lambda category_id: None)
    monkeypatch.setattr(vocabulary_db, "words", lambda **kwargs: None)
    monkeypatch.setattr(vocabulary_db, "word_count", lambda **kwargs: None)
    monkeypatch.setattr(vocabulary_db, "word", lambda word_id: None)
    with TestClient(main.app) as c:
        yield c


def audio_upload():
    return {"audio": ("clip.m4a", b"fake-audio-bytes", "audio/mp4")}


# ---------------------------------------------------------------- basics


def test_health_reports_ml_status(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert set(body["ml"]) == {"transcribe", "translate", "pronunciation"}


def test_categories_and_word(client):
    assert client.get("/api/categories").status_code == 200
    assert client.get("/api/words/word_001").status_code == 200
    assert client.get("/api/words/nope").status_code == 404


# ------------------------------------------------------------ transcribe


def test_transcribe_stub(client, monkeypatch):
    monkeypatch.setattr(ml_adapters, "_transcribe", None)
    r = client.post("/api/transcribe", files=audio_upload())
    assert r.status_code == 200
    assert r.json()["stub"] is True


@pytest.mark.parametrize(
    "status, code", [("empty_audio", 422), ("no_speech", 422), ("model_error", 503)]
)
def test_transcribe_failure_statuses(client, monkeypatch, status, code):
    monkeypatch.setattr(
        ml_adapters,
        "transcribe_audio",
        lambda audio, language: {"status": status, "text": "", "confidence": 0.0, "stub": False},
    )
    r = client.post("/api/transcribe", files=audio_upload())
    assert r.status_code == code
    assert r.json()["status"] == status


def test_transcribe_bad_language_is_400(client, monkeypatch):
    def boom(audio, language):
        raise ValueError("unsupported language")

    monkeypatch.setattr(ml_adapters, "transcribe_audio", boom)
    r = client.post("/api/transcribe", files=audio_upload(), data={"language": "xx"})
    assert r.status_code == 400


def test_transcribe_requires_audio(client):
    assert client.post("/api/transcribe").status_code == 422


# ------------------------------------------------------------- translate


def test_translate_known_phrase(client):
    r = client.post("/api/translate", json={"text": "Take your pills."})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "translated"
    assert body["translated_text"]
    assert body["verified"] is False


def test_translate_unknown_phrase_is_pending(client):
    r = client.post("/api/translate", json={"text": "zzzz qqqq xxxx wwww"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending_translation"
    assert body["translated_text"] is None


def test_translate_bad_language_pair(client):
    r = client.post("/api/translate", json={"text": "hi", "source_language": "fr"})
    assert r.status_code == 400


def test_translate_empty_text(client):
    assert client.post("/api/translate", json={"text": "  "}).status_code == 422


# --------------------------------------------------------- pronunciation


def test_pronunciation_stub_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(ml_adapters, "_score", None)
    r = client.post(
        "/api/pronunciation/score", files=audio_upload(), data={"target_text": "hello"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "scoring_unavailable"
    assert body["score"] is None
    assert body["stub"] is True


def test_pronunciation_uses_real_scorer(client, monkeypatch):
    monkeypatch.setattr(
        ml_adapters, "_score", lambda audio, target: {"score": 91, "feedback": "Nice."}
    )
    r = client.post(
        "/api/pronunciation/score", files=audio_upload(), data={"word_id": "word_001"}
    )
    body = r.json()
    assert body["status"] == "scored"
    assert body["score"] == 91
    assert body["target_text"]  # filled in from the word


def test_pronunciation_needs_target(client):
    r = client.post("/api/pronunciation/score", files=audio_upload())
    assert r.status_code == 422


def test_pronunciation_unknown_word(client):
    r = client.post("/api/pronunciation/score", files=audio_upload(), data={"word_id": "nope"})
    assert r.status_code == 404
