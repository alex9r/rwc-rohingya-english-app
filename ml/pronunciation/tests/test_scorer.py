"""Tests for ml.pronunciation.scorer. A fake transcriber stands in for Whisper, so
these run offline and fast. Run: python -m pytest ml/pronunciation -q"""

import io
import json

import pytest

from ml.pronunciation import MIN_CONFIDENCE, normalize, score_pronunciation
from ml.speech import Status, TranscriptionResult


def fake(text="", confidence=0.9, status=Status.OK):
    """A transcriber that ignores the audio and returns a canned result."""
    calls = []

    def transcriber(audio, language=None):
        calls.append(language)
        return TranscriptionResult(status=status, text=text, confidence=confidence)

    transcriber.calls = calls
    return transcriber


def score(text, target, **kw):
    return score_pronunciation(b"audio", target, transcriber=fake(text, **kw))


# --------------------------------------------------------------------------- normalize


def test_normalize_case_punctuation_contractions_numbers():
    assert normalize("I'm 2 years old, Doctor!") == ["i", "am", "two", "years", "old", "doctor"]
    assert normalize("Don’t go; it's late.") == ["do", "not", "go", "it", "is", "late"]
    assert normalize("twenty-one") == ["twenty", "one"]
    assert normalize("21") == ["twenty", "one"]
    assert normalize("John's bag") == ["john", "bag"]
    assert normalize("...!?") == []
    assert normalize(None) == []


# --------------------------------------------------------------------------- scoring


def test_exact_match():
    r = score("I need a doctor", "I need a doctor")
    assert r.status == "scored" and r.score == 100
    assert r.matched_words == ["i", "need", "a", "doctor"]
    assert r.missed_words == [] and r.needs_improvement == []
    assert r.feedback_code == "great"


def test_one_word_wrong():
    r = score("I need a dentist", "I need a doctor")
    assert r.score == 75
    assert r.missed_words == ["doctor"]
    assert r.needs_improvement == [{"word": "doctor", "heard": "dentist", "issue": "different"}]
    assert r.feedback_code == "good"


def test_missing_word():
    r = score("I need doctor", "I need a doctor")
    assert r.score == 75
    assert r.needs_improvement == [{"word": "a", "heard": None, "issue": "missed"}]


def test_extra_word_costs_half():
    r = score("I really need a doctor", "I need a doctor")
    assert r.missed_words == []
    assert r.needs_improvement == [{"word": None, "heard": "really", "issue": "extra"}]
    assert r.score == round(100 * 4 / 4.5)


def test_punctuation_and_case_ignored():
    assert score("i NEED a doctor!!", "I need a doctor.").score == 100
    assert score("I am fine", "I'm fine").score == 100
    assert score("I have two children", "I have 2 children").score == 100


def test_homophone_not_penalised():
    assert score("their house", "there house").score == 100
    assert score("I want to buy bread", "I want too by bread").score == 100


def test_close_word_gets_partial_credit_and_is_flagged():
    r = score("two doctors", "two doctor")
    assert 90 <= r.score < 100
    assert r.needs_improvement == [{"word": "doctor", "heard": "doctors", "issue": "close"}]


def test_threshold_is_configurable():
    strict = score_pronunciation(b"a", "two doctor", transcriber=fake("two doctors"), fuzzy_threshold=0.99)
    assert strict.missed_words == ["doctor"]


def test_completely_wrong_sentence_scores_low():
    r = score("where is the bus stop", "I need a doctor")
    assert r.score == 0 and r.feedback_code == "try_again"


# --------------------------------------------------------------------------- unavailable


def test_empty_target_does_not_call_transcriber():
    t = fake("hello")
    for target in ("", "   ", "...", None):
        r = score_pronunciation(b"x", target, transcriber=t)
        assert r.status == "scoring_unavailable" and r.score is None
        assert r.feedback_code == "invalid_target"
    assert t.calls == []


def test_low_confidence_not_scored():
    r = score("I need a doctor", "I need a doctor", confidence=MIN_CONFIDENCE - 0.01)
    assert r.status == "scoring_unavailable" and r.score is None
    assert r.feedback_code == "low_confidence"
    assert r.transcript == "I need a doctor"


def test_confidence_at_threshold_is_scored():
    assert score("hello", "hello", confidence=MIN_CONFIDENCE).status == "scored"


def test_unusable_transcript_not_scored():
    r = score("...", "hello")
    assert r.status == "scoring_unavailable" and r.feedback_code == "unclear_transcript"


@pytest.mark.parametrize("status", [s for s in Status if s is not Status.OK])
def test_transcribe_statuses_pass_through(status):
    r = score_pronunciation(b"x", "hello", transcriber=fake(status=status))
    assert r.status == status.value and r.score is None
    assert r.feedback and r.feedback_code == status.value


def test_transcriber_exception_becomes_model_error():
    def boom(audio, language=None):
        raise RuntimeError("model blew up")

    r = score_pronunciation(b"x", "hello", transcriber=boom)
    assert r.status == "model_error" and r.score is None


def test_language_is_english():
    t = fake("hello")
    score_pronunciation(b"x", "hello", transcriber=t)
    assert t.calls == ["en"]


# --------------------------------------------------------------------------- contract


def test_to_dict_shape_is_json_ready():
    d = score("I need a dentist", "I need a doctor").to_dict()
    assert set(d) == {
        "score", "max_score", "status", "transcript", "confidence", "matched_words",
        "missed_words", "needs_improvement", "feedback", "feedback_code", "score_basis",
        "provisional",
    }
    assert d["max_score"] == 100 and d["score_basis"] == "asr_match" and d["provisional"] is True
    json.dumps(d)


def test_unscored_result_is_also_provisional():
    d = score_pronunciation(b"x", "", transcriber=fake()).to_dict()
    assert d["provisional"] is True and d["score"] is None


# --------------------------------------------------------------------------- real transcribe(), no model


def test_real_transcribe_silent_audio_is_no_speech():
    """Uses the real ml.speech.transcribe; silent audio is rejected before any model
    loads, so this stays offline."""
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    r = score_pronunciation(buf.getvalue(), "hello")
    assert r.status == "no_speech" and r.score is None


def test_real_transcribe_empty_and_corrupt():
    assert score_pronunciation(b"", "hello").status == "empty_audio"
    assert score_pronunciation(b"not audio at all", "hello").status == "invalid_audio"
    assert score_pronunciation(12345, "hello").status == "invalid_audio"  # wrong type: still no raise
