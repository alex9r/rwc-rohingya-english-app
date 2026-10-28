"""Tests for ml.speech.transcribe. A fake model stands in for Whisper, so these run
offline and fast (no weights download). Run: python -m pytest ml/speech -q"""

import io
import json
import shutil
import subprocess
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from ml.speech import LOW_CONFIDENCE, Status, transcribe
from ml.speech.transcribe import SAMPLE_RATE, segment_confidence


# --------------------------------------------------------------------------- helpers


def wav_bytes(seconds: float, freq: float | None = 220.0, amp: float = 0.3, rate: int = SAMPLE_RATE) -> bytes:
    n = int(seconds * rate)
    t = np.arange(n) / rate
    x = amp * np.sin(2 * np.pi * freq * t) if freq else np.zeros(n)
    pcm = (x * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def seg(text, start=0.0, end=1.0, logprob=-0.1, no_speech=0.01, ratio=1.2):
    return SimpleNamespace(start=start, end=end, text=text, avg_logprob=logprob,
                           no_speech_prob=no_speech, compression_ratio=ratio)


class FakeModel:
    def __init__(self, segments=(), language="bn", prob=0.9, error=None):
        self.segments, self.language, self.prob, self.error = list(segments), language, prob, error
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        if self.error:
            raise self.error
        return iter(self.segments), SimpleNamespace(language=self.language, language_probability=self.prob)


@pytest.fixture
def speech_file(tmp_path):
    p = tmp_path / "speech.wav"
    p.write_bytes(wav_bytes(1.5))
    return p


# --------------------------------------------------------------------------- failure paths


def test_missing_file_is_invalid(tmp_path):
    r = transcribe(tmp_path / "nope.wav", model=FakeModel())
    assert r.status == Status.INVALID_AUDIO and r.text == "" and r.confidence == 0.0
    assert "not found" in r.error


def test_zero_byte_file_is_empty(tmp_path):
    p = tmp_path / "empty.m4a"
    p.write_bytes(b"")
    assert transcribe(p, model=FakeModel()).status == Status.EMPTY_AUDIO


def test_empty_bytes_is_empty():
    assert transcribe(b"", model=FakeModel()).status == Status.EMPTY_AUDIO


def test_garbage_bytes_is_invalid():
    r = transcribe(b"this is definitely not audio" * 50, model=FakeModel())
    assert r.status == Status.INVALID_AUDIO
    assert r.error


def test_wav_header_with_no_frames_is_empty():
    r = transcribe(wav_bytes(0.0), model=FakeModel())
    assert r.status in (Status.EMPTY_AUDIO, Status.INVALID_AUDIO)


def test_too_short():
    model = FakeModel([seg("hi")])
    r = transcribe(wav_bytes(0.1), model=model)
    assert r.status == Status.TOO_SHORT and r.duration_s == pytest.approx(0.1, abs=0.02)
    assert model.calls == []  # never reached the model


def test_too_long():
    r = transcribe(wav_bytes(61.0), model=FakeModel([seg("hi")]))
    assert r.status == Status.TOO_LONG


def test_silence_skips_model():
    model = FakeModel([seg("Thank you.")])  # Whisper's classic silence hallucination
    r = transcribe(wav_bytes(2.0, freq=None), model=model)
    assert r.status == Status.NO_SPEECH and r.text == ""
    assert model.calls == []


def test_model_returns_nothing_is_no_speech(speech_file):
    r = transcribe(speech_file, model=FakeModel([]))
    assert r.status == Status.NO_SPEECH and r.language == "bn"


def test_model_returns_only_blank_segments_is_no_speech(speech_file):
    assert transcribe(speech_file, model=FakeModel([seg("   ")])).status == Status.NO_SPEECH


def test_model_crash_is_reported_not_raised(speech_file):
    r = transcribe(speech_file, model=FakeModel(error=RuntimeError("CUDA out of memory")))
    assert r.status == Status.MODEL_ERROR and "CUDA out of memory" in r.error


def test_unknown_language_raises():
    with pytest.raises(ValueError, match="Rohingya"):
        transcribe(b"x", language="rhg", model=FakeModel())


def test_wrong_input_type_raises():
    with pytest.raises(TypeError):
        transcribe(12345, model=FakeModel())


# --------------------------------------------------------------------------- happy path


def test_ok_from_path(speech_file):
    model = FakeModel([seg("ami bajar zaiyum", 0.0, 1.2, logprob=-0.2)])
    r = transcribe(speech_file, language="bn", model=model)
    assert r.ok and r.status == Status.OK
    assert r.text == "ami bajar zaiyum"
    assert 0 < r.confidence <= 1
    assert r.language == "bn" and r.duration_s == pytest.approx(1.5, abs=0.02)
    assert r.processing_s is not None
    audio, kwargs = model.calls[0]
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert kwargs["language"] == "bn" and kwargs["condition_on_previous_text"] is False


def test_ok_from_bytes_and_file_object(speech_file):
    data = speech_file.read_bytes()
    assert transcribe(data, model=FakeModel([seg("a")])).ok
    assert transcribe(io.BytesIO(data), model=FakeModel([seg("a")])).ok


def test_stereo_44k_is_resampled(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    p = tmp_path / "stereo.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1",
                    "-ac", "2", "-ar", "44100", str(p)], check=True)
    model = FakeModel([seg("a")])
    r = transcribe(p, model=model)
    assert r.ok and r.duration_s == pytest.approx(1.0, abs=0.05)
    assert model.calls[0][0].size == pytest.approx(SAMPLE_RATE, rel=0.05)


def test_m4a_like_expo_recording(tmp_path):
    """Expo's HIGH_QUALITY preset records AAC in .m4a; make sure it decodes, from bytes too."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    p = tmp_path / "rec.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1.2",
                    "-ac", "1", "-ar", "44100", "-c:a", "aac", str(p)], check=True)
    assert transcribe(p, model=FakeModel([seg("a")])).ok
    assert transcribe(p.read_bytes(), model=FakeModel([seg("a")])).ok


def test_segments_joined_and_to_dict_is_json(speech_file):
    r = transcribe(speech_file, model=FakeModel([seg("hello", 0, 0.5), seg("doctor", 0.5, 1.2)]))
    assert r.text == "hello doctor" and len(r.segments) == 2
    d = json.loads(json.dumps(r.to_dict()))
    assert d["status"] == "ok" and d["text"] == "hello doctor"
    assert set(d) >= {"text", "confidence", "is_confident", "status", "error", "segments"}


def test_failure_to_dict_is_json():
    d = json.loads(json.dumps(transcribe(b"", model=FakeModel()).to_dict()))
    assert d["status"] == "empty_audio" and d["is_confident"] is False and d["text"] == ""


# --------------------------------------------------------------------------- confidence


def test_confidence_bounds_and_ordering():
    assert segment_confidence(0.0, 0.0, 1.0) == 1.0
    assert segment_confidence(-float("inf"), 0.0, 1.0) == 0.0
    assert segment_confidence(float("nan"), 0.0, 1.0) == 0.0
    assert segment_confidence(-0.1, 0.0, 1.0) > segment_confidence(-1.5, 0.0, 1.0)


def test_confidence_penalises_no_speech_and_repetition():
    base = segment_confidence(-0.2, 0.0, 1.2)
    assert segment_confidence(-0.2, 0.8, 1.2) < base * 0.25
    assert segment_confidence(-0.2, 0.0, 3.0) == pytest.approx(base * 0.5)


def test_overall_confidence_is_duration_weighted(speech_file):
    long_good = seg("clear sentence here", 0.0, 1.0, logprob=-0.05)
    short_bad = seg("uh", 1.0, 1.1, logprob=-2.5)
    r = transcribe(speech_file, model=FakeModel([long_good, short_bad]))
    assert r.confidence > 0.85


def test_low_confidence_flag(speech_file):
    r = transcribe(speech_file, model=FakeModel([seg("mumble", logprob=-1.5)]))
    assert r.ok and r.confidence < LOW_CONFIDENCE and r.is_confident is False
