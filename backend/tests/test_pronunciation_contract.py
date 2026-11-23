"""Pins /api/pronunciation/score to Luna's real ml.pronunciation scorer.

The scorer runs for real; only the Whisper step is faked (a transcriber that returns
a canned TranscriptionResult), so no model weights are needed. Bad-audio cases go
through the real ml.speech.transcribe, which rejects them before any model runs.
If ml.pronunciation changes its result fields or statuses, this fails.
"""

import io
import wave

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("av")
pronunciation = pytest.importorskip("ml.pronunciation")
speech = pytest.importorskip("ml.speech")

from app import db, main, ml_adapters  # noqa: E402


def heard(text: str, confidence: float = 0.9, status: str = "ok"):
    """A fake Whisper step: ignores the audio and returns this transcript."""
    result = speech.TranscriptionResult(status=speech.Status(status), text=text,
                                        confidence=confidence)

    def transcriber(audio, language=None, **kwargs):
        assert language == "en"  # the scorer must always ask for English
        return result

    return transcriber


def use_scorer(monkeypatch, transcriber=None):
    """Point the API at the real scorer, with or without a fake transcriber."""

    def score(audio, target):
        if transcriber is None:
            return pronunciation.score_pronunciation(audio, target)
        return pronunciation.score_pronunciation(audio, target, transcriber=transcriber)

    monkeypatch.setattr(ml_adapters, "_score", score)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(ml_adapters, "_warmup", None)
    with TestClient(main.app) as c:
        yield c


def upload(audio: bytes = b"fake-audio-bytes"):
    return {"audio": ("clip.m4a", audio, "audio/mp4")}


def silent_wav(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * int(16_000 * seconds))
    return buf.getvalue()


# ------------------------------------------------------------- scored


def test_exact_match_scores_100(client, monkeypatch):
    use_scorer(monkeypatch, heard("I need a doctor."))
    r = client.post("/api/pronunciation/score", files=upload(),
                    data={"target_text": "I need a doctor"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "scored"
    assert body["score"] == 100 and body["max_score"] == 100
    assert body["feedback_code"] == "great"
    assert body["missed_words"] == [] and body["needs_improvement"] == []
    assert body["transcript"] == "I need a doctor."
    assert body["stub"] is False


def test_wrong_word_is_reported(client, monkeypatch):
    use_scorer(monkeypatch, heard("I need a dentist"))
    body = client.post("/api/pronunciation/score", files=upload(),
                       data={"target_text": "I need a doctor"}).json()
    assert body["status"] == "scored"
    assert body["score"] == 75  # 3 of 4 words
    assert body["missed_words"] == ["doctor"]
    assert body["matched_words"] == ["i", "need", "a"]
    assert body["needs_improvement"] == [
        {"word": "doctor", "heard": "dentist", "issue": "different"}
    ]


def test_response_is_marked_provisional(client, monkeypatch):
    use_scorer(monkeypatch, heard("hello"))
    body = client.post("/api/pronunciation/score", files=upload(),
                       data={"target_text": "hello"}).json()
    assert body["provisional"] is True
    assert body["score_basis"] == "asr_match"


def test_word_id_supplies_the_target(client, monkeypatch):
    english = main.WORD_INDEX["word_001"][1]["english"]
    use_scorer(monkeypatch, heard(english))
    body = client.post("/api/pronunciation/score", files=upload(),
                       data={"word_id": "word_001"}).json()
    assert body["word_id"] == "word_001"
    assert body["target_text"] == english
    assert body["score"] == 100


def test_contract_fields_are_all_present(client, monkeypatch):
    use_scorer(monkeypatch, heard("hello"))
    body = client.post("/api/pronunciation/score", files=upload(),
                       data={"target_text": "hello"}).json()
    # The app and docs/pronunciation-api-contract.md depend on these names.
    assert set(body) >= {
        "word_id", "target_text", "score", "max_score", "status", "transcript", "confidence",
        "matched_words", "missed_words", "needs_improvement", "feedback", "feedback_code",
        "score_basis", "provisional", "stub",
    }


# ------------------------------------------------- scoring_unavailable (200)


def test_low_asr_confidence_gives_no_score(client, monkeypatch):
    use_scorer(monkeypatch, heard("I need a doctor", confidence=0.1))
    r = client.post("/api/pronunciation/score", files=upload(),
                    data={"target_text": "I need a doctor"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "scoring_unavailable"
    assert body["score"] is None
    assert body["feedback_code"] == "low_confidence"
    assert body["feedback"]  # the app can show this as is


def test_unusable_transcript_gives_no_score(client, monkeypatch):
    use_scorer(monkeypatch, heard("..."))
    body = client.post("/api/pronunciation/score", files=upload(),
                       data={"target_text": "hello"}).json()
    assert body["status"] == "scoring_unavailable"
    assert body["feedback_code"] == "unclear_transcript"


def test_target_with_no_words_gives_no_score(client, monkeypatch):
    use_scorer(monkeypatch, heard("hello"))
    body = client.post("/api/pronunciation/score", files=upload(),
                       data={"target_text": "?!"}).json()
    assert body["status"] == "scoring_unavailable"
    assert body["feedback_code"] == "invalid_target"


# -------------------------------------------- bad audio (200, real transcribe)


@pytest.mark.parametrize(
    "audio, status",
    [
        (b"", "empty_audio"),
        (b"not audio at all" * 100, "invalid_audio"),
        (silent_wav(0.1), "too_short"),
        (silent_wav(1.0), "no_speech"),
    ],
)
def test_bad_audio_is_a_200_with_feedback(client, monkeypatch, audio, status):
    # The scorer always asks for language="en", and transcribe checks that code against
    # faster-whisper's language list, so the package must be installed (no model loads).
    pytest.importorskip("faster_whisper")
    use_scorer(monkeypatch)
    r = client.post("/api/pronunciation/score", files=upload(audio),
                    data={"target_text": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == status
    assert body["score"] is None
    assert body["feedback"]
    assert body["stub"] is False


# ------------------------------------------------------------ server errors


def test_model_error_is_503(client, monkeypatch):
    def broken(audio, language=None, **kwargs):
        raise RuntimeError("model blew up")

    use_scorer(monkeypatch, broken)  # the scorer turns any transcriber exception into model_error
    r = client.post("/api/pronunciation/score", files=upload(),
                    data={"target_text": "hello"})
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "model_error"
    assert body["score"] is None


# ------------------------------------------------------------ request checks


def test_only_english_can_be_scored(client, monkeypatch):
    use_scorer(monkeypatch, heard("hello"))
    r = client.post("/api/pronunciation/score", files=upload(),
                    data={"target_text": "hello", "language": "rhg"})
    assert r.status_code == 422


def test_oversized_upload_is_413(client, monkeypatch):
    use_scorer(monkeypatch, heard("hello"))
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
    r = client.post("/api/pronunciation/score", files=upload(b"x" * 100),
                    data={"target_text": "hello"})
    assert r.status_code == 413


# ------------------------------------------------------------- wiring


def test_adapter_finds_the_real_scorer_when_whisper_is_installed():
    """ml_adapters must import ml.pronunciation (it once looked in ml.speech)."""
    pytest.importorskip("faster_whisper")
    assert ml_adapters._score is pronunciation.score_pronunciation


def test_health_reports_pronunciation_real_or_stub(client, monkeypatch):
    use_scorer(monkeypatch, heard("hello"))
    assert client.get("/health").json()["ml"]["pronunciation"] == "real"
    monkeypatch.setattr(ml_adapters, "_score", None)
    assert client.get("/health").json()["ml"]["pronunciation"] == "stub"
