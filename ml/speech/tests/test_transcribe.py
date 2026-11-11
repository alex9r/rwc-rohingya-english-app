"""Tests for ml.speech.transcribe. A fake model stands in for Whisper, so these run
offline and fast (no weights download). Run: python -m pytest ml/speech -q"""

import io
import json
import math
import wave
from types import SimpleNamespace

import av
import numpy as np
import pytest

from ml.speech import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    MAX_ATTEMPTS,
    Action,
    ConfidenceLevel,
    Status,
    classify_confidence,
    transcribe,
)
from ml.speech.calibrate import load_clips, recommend
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


def encoded_tone(path, seconds: float, rate: int, channels: int, codec: str) -> None:
    """Write a 300 Hz tone with PyAV (no ffmpeg binary needed), e.g. AAC into .m4a."""
    with av.open(str(path), "w") as out:
        stream = out.add_stream(codec, rate=rate, layout="stereo" if channels == 2 else "mono")
        fmt = stream.codec_context.format.name
        step = stream.codec_context.frame_size or 1024
        n = int(seconds * rate)
        x = (0.3 * np.sin(2 * np.pi * 300 * np.arange(n) / rate)).astype(np.float32)
        for i in range(0, n, step):
            chunk = np.tile(x[i : i + step], (channels, 1))  # planar: one row per channel
            if fmt == "s16":  # packed int16: interleave channels into one row
                chunk = (chunk * 32767).astype(np.int16).reshape(1, -1, order="F")
            frame = av.AudioFrame.from_ndarray(chunk, format=fmt, layout=stream.layout.name)
            frame.sample_rate = rate
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):  # flush
            out.mux(packet)


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
    assert r.error and ".audio" not in r.error  # no server temp path in the response


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
    p = tmp_path / "stereo.wav"
    encoded_tone(p, 1.0, rate=44100, channels=2, codec="pcm_s16le")
    model = FakeModel([seg("a")])
    r = transcribe(p, model=model)
    assert r.ok and r.duration_s == pytest.approx(1.0, abs=0.05)
    assert model.calls[0][0].size == pytest.approx(SAMPLE_RATE, rel=0.05)


def test_m4a_like_expo_recording(tmp_path):
    """Expo's HIGH_QUALITY preset records AAC in .m4a; make sure it decodes, from bytes too."""
    p = tmp_path / "rec.m4a"
    encoded_tone(p, 1.2, rate=44100, channels=1, codec="aac")
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


# --------------------------------------------------------------------------- levels and actions


def scored(confidence, start=0.0, end=1.0):
    """A fake Whisper segment that comes out at this confidence."""
    return seg("words", start, end, logprob=math.log(confidence), no_speech=0.0)


HIGH_SCORE = min(HIGH_CONFIDENCE + 0.05, 1.0)
MEDIUM_SCORE = (LOW_CONFIDENCE + HIGH_CONFIDENCE) / 2
LOW_SCORE = LOW_CONFIDENCE - 0.05


def test_thresholds_leave_room_for_a_medium_band():
    assert 0 < LOW_CONFIDENCE < HIGH_CONFIDENCE <= 1
    assert MAX_ATTEMPTS >= 2  # at least one repeat


@pytest.mark.parametrize("score, expected", [
    (HIGH_CONFIDENCE, ConfidenceLevel.HIGH),  # a threshold belongs to the band above it
    (HIGH_CONFIDENCE - 0.001, ConfidenceLevel.MEDIUM),
    (LOW_CONFIDENCE, ConfidenceLevel.MEDIUM),
    (LOW_CONFIDENCE - 0.001, ConfidenceLevel.LOW),
    (0.0, ConfidenceLevel.LOW),
    (1.0, ConfidenceLevel.HIGH),
])
def test_classify_boundaries(score, expected):
    assert classify_confidence(score) == expected


def test_one_weak_segment_rules_out_high():
    assert classify_confidence(0.95, weakest_segment=LOW_SCORE) == ConfidenceLevel.MEDIUM
    assert classify_confidence(0.95, weakest_segment=LOW_CONFIDENCE) == ConfidenceLevel.HIGH
    assert classify_confidence(LOW_SCORE, weakest_segment=0.95) == ConfidenceLevel.LOW


@pytest.mark.parametrize("score, level, action, reason", [
    (HIGH_SCORE, "high", "accept", None),
    (MEDIUM_SCORE, "medium", "confirm", None),
    (LOW_SCORE, "low", "ask_repeat", "low_confidence"),
])
def test_pipeline_sets_level_and_action(speech_file, score, level, action, reason):
    r = transcribe(speech_file, model=FakeModel([scored(score)]))
    assert r.ok and r.confidence == pytest.approx(score, abs=0.001)
    d = json.loads(json.dumps(r.to_dict()))
    assert (d["confidence_level"], d["action"], d["reason"]) == (level, action, reason)
    assert d["text"] == "words"  # the best guess is kept even when it isn't trusted


def test_clear_sentence_with_garbled_phrase_gets_confirmed(speech_file):
    clear, garbled = scored(0.95, 0.0, 10.0), scored(LOW_SCORE, 10.0, 10.5)
    r = transcribe(speech_file, model=FakeModel([clear, garbled]))
    assert r.confidence >= HIGH_CONFIDENCE
    assert r.confidence_level == ConfidenceLevel.MEDIUM and r.action == Action.CONFIRM


def test_low_confidence_asks_to_repeat_then_falls_back(speech_file):
    actions = [
        transcribe(speech_file, model=FakeModel([scored(LOW_SCORE)]), attempt=n).action
        for n in range(1, MAX_ATTEMPTS + 2)  # one past the limit stays on fallback
    ]
    assert actions == [Action.ASK_REPEAT] * (MAX_ATTEMPTS - 1) + [Action.FALLBACK] * 2


def test_fallback_keeps_reason_and_best_guess(speech_file):
    r = transcribe(speech_file, model=FakeModel([scored(LOW_SCORE)]), attempt=MAX_ATTEMPTS)
    assert r.action == Action.FALLBACK and r.reason == "low_confidence"
    assert r.text == "words" and r.attempt == MAX_ATTEMPTS


def test_a_good_repeat_is_accepted_on_the_last_attempt(speech_file):
    r = transcribe(speech_file, model=FakeModel([scored(HIGH_SCORE)]), attempt=MAX_ATTEMPTS)
    assert r.action == Action.ACCEPT and r.reason is None


@pytest.mark.parametrize("audio, status", [
    (b"", "empty_audio"),
    (b"this is definitely not audio" * 50, "invalid_audio"),
    (wav_bytes(0.1), "too_short"),
    (wav_bytes(61.0), "too_long"),
    (wav_bytes(2.0, freq=None), "no_speech"),
])
def test_unusable_audio_asks_to_repeat_with_its_status_as_reason(audio, status):
    r = transcribe(audio, model=FakeModel())
    assert r.status.value == status and r.confidence_level is None
    assert r.action == Action.ASK_REPEAT and r.reason == status
    assert transcribe(audio, model=FakeModel(), attempt=MAX_ATTEMPTS).action == Action.FALLBACK


def test_unrecognised_speech_asks_to_repeat(speech_file):
    r = transcribe(speech_file, model=FakeModel([]))
    assert r.action == Action.ASK_REPEAT and r.reason == "no_speech"


def test_model_error_never_blames_the_user(speech_file):
    for attempt in (1, MAX_ATTEMPTS):
        r = transcribe(speech_file, model=FakeModel(error=RuntimeError("boom")), attempt=attempt)
        assert r.action == Action.RETRY_LATER and r.reason is None and r.confidence_level is None


def test_failure_to_dict_includes_handling_fields():
    d = json.loads(json.dumps(transcribe(b"", model=FakeModel()).to_dict()))
    assert d["confidence_level"] is None and d["action"] == "ask_repeat"
    assert d["reason"] == "empty_audio" and d["attempt"] == 1


def test_attempt_below_one_raises():
    with pytest.raises(ValueError, match="attempt"):
        transcribe(b"x", model=FakeModel(), attempt=0)


# --------------------------------------------------------------------------- calibrate


def test_recommend_separates_clear_from_poor_clips():
    clips = [(0.9, 0.0)] * 10 + [(0.7, 0.2)] * 10 + [(0.3, 0.9)] * 10
    high, low = recommend(clips, accept_wer=0.05, repeat_wer=0.50)
    assert high == 0.75  # any lower lets the 0.2-WER clips in, averaging 0.10
    assert low == 0.4  # the first line with only the poor group just below it


def test_low_line_is_not_pulled_up_by_very_bad_clips_far_below():
    # Averaging everything below 0.75 would give 0.55 and ask the 0.7 clips to repeat.
    clips = [(0.7, 0.2)] * 10 + [(0.2, 0.9)] * 10
    assert recommend(clips, accept_wer=0.10, repeat_wer=0.50)[1] == 0.3


def test_recommend_returns_none_when_targets_are_out_of_reach():
    assert recommend([(0.9, 0.6)] * 10, accept_wer=0.10, repeat_wer=0.90) == (None, None)


def test_recommend_ignores_bands_with_too_few_clips():
    clips = [(0.9, 0.0)] * 2 + [(0.5, 0.5)] * 20
    assert recommend(clips, accept_wer=0.10, repeat_wer=0.90)[0] is None


def test_load_clips_skips_failed_rows(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text("file,confidence,wer\na.wav,0.9,0.1\nb.wav,0.0,\n", encoding="utf-8")
    assert load_clips(p) == [(0.9, 0.1)]


def test_load_clips_needs_a_wer_column(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text("file,confidence\na.wav,0.9\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="wer"):
        load_clips(p)
