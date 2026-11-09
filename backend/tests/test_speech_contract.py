"""Pins /api/transcribe to Mohammed's real ml.speech.transcribe.

Only inputs rejected before the model runs (empty, garbage, silent, too short), so
no Whisper weights are needed. If ml.speech changes its statuses, this fails.
"""

import io
import wave

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("av")
speech = pytest.importorskip("ml.speech")

from app import db, main, ml_adapters  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(ml_adapters, "_transcribe", speech.transcribe)
    monkeypatch.setattr(ml_adapters, "_warmup", None)  # don't load a model
    with TestClient(main.app) as c:
        yield c


def silent_wav(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * int(16_000 * seconds))
    return buf.getvalue()


@pytest.mark.parametrize(
    "audio, status",
    [
        (b"", "empty_audio"),
        (b"not audio at all" * 100, "invalid_audio"),
        (silent_wav(0.1), "too_short"),
        (silent_wav(1.0), "no_speech"),
    ],
)
def test_bad_audio_returns_422_with_status(client, audio, status):
    r = client.post("/api/transcribe", files={"audio": ("clip.wav", audio, "audio/wav")})
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == status
    assert body["stub"] is False
    assert body["text"] == "" and body["confidence"] == 0.0


def test_rhg_is_rejected_with_400(client):
    r = client.post(
        "/api/transcribe",
        files={"audio": ("clip.wav", silent_wav(1.0), "audio/wav")},
        data={"language": "rhg"},
    )
    assert r.status_code == 400

    
