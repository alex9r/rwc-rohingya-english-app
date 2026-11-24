"""Logic tests with made-up embeddings and a fake embedder. No model is loaded."""

import wave

import numpy as np
import pytest

from ml.embedscore import compare, dtw_distance
from ml.embedscore.embed import pool, trim_silence

RNG = np.random.default_rng(0)
SEQ = RNG.normal(size=(40, 16)).astype(np.float32)


def test_identical_sequences_have_zero_distance():
    assert dtw_distance(SEQ, SEQ) == pytest.approx(0.0, abs=1e-5)


def test_distance_is_symmetric():
    other = RNG.normal(size=(55, 16)).astype(np.float32)
    assert dtw_distance(SEQ, other) == pytest.approx(dtw_distance(other, SEQ), rel=1e-5)


def test_speaking_speed_barely_matters_but_content_does():
    slower = np.repeat(SEQ, 2, axis=0)                     # same content, half speed
    different = RNG.normal(size=(40, 16)).astype(np.float32)
    assert dtw_distance(SEQ, slower) < 0.05
    assert dtw_distance(SEQ, different) > 0.5


def test_bad_shapes_raise():
    with pytest.raises(ValueError):
        dtw_distance(SEQ, SEQ[:, :8])
    with pytest.raises(ValueError):
        dtw_distance(SEQ[:0], SEQ)


def test_trim_and_pool():
    x = np.concatenate([np.zeros(3200), np.ones(6400) * 0.5, np.zeros(3200)]).astype(np.float32)
    assert len(trim_silence(x)) == 6400
    assert pool(np.arange(10, dtype=np.float32).reshape(5, 2), 2).shape == (2, 2)


def _wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def _fake_embedder(samples, layers):
    """Frames of a spectrum-like feature, so different tones give different embeddings."""
    n = len(samples) // 640
    frames = samples[: n * 640].reshape(n, 640)
    feats = np.abs(np.fft.rfft(frames, axis=1))[:, :32]
    return {l: feats.astype(np.float32) for l in layers}


def _tones(freqs, seconds=0.3):
    t = np.arange(int(16000 * seconds)) / 16000
    return np.concatenate([0.5 * np.sin(2 * np.pi * f * t) for f in freqs]).astype(np.float32)


def test_compare_close_for_same_content_far_for_different(tmp_path):
    ref = _wav(tmp_path / "ref.wav", _tones([300, 600, 900]))
    same = _wav(tmp_path / "same.wav", _tones([300, 600, 900], 0.4))     # slower reading
    other = _wav(tmp_path / "other.wav", _tones([1200, 200, 1500]))
    near = compare(same, ref, embedder=_fake_embedder)
    far = compare(other, ref, embedder=_fake_embedder)
    assert near.status == "ok" and far.status == "ok"
    assert near.distance < far.distance and near.provisional is True


def test_compare_never_raises(tmp_path):
    ref = _wav(tmp_path / "ref.wav", _tones([300]))
    assert compare(b"not audio", ref, embedder=_fake_embedder).status == "invalid_audio"
    assert compare(12345, ref, embedder=_fake_embedder).status == "invalid_audio"

    def boom(samples, layers):
        raise RuntimeError("model failed")

    r = compare(ref, ref, embedder=boom)
    assert r.status == "model_error" and "model failed" in r.error and r.distance is None
