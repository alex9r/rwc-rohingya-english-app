"""Offline tests for ml.tts. A fake backend stands in for the real engine, so no model
download is needed. Run: python -m pytest ml/tts -q"""

import datetime as dt
import io
import json

import av
import numpy as np
import pytest

from ml.tts import WordItem, available_backends, generate, get_backend, load_words, register_backend, select_words
from ml.tts.backends import to_mp3
from ml.tts.generate import HERO_IDS, SUFFIX


class FakeBackend:
    name = "fake"
    voice = "fake_voice"
    license_note = "test only"

    def __init__(self, fail_on=()):
        self.fail_on, self.heard = set(fail_on), []

    def synthesize(self, text):
        self.heard.append(text)
        if text in self.fail_on:
            raise RuntimeError("engine blew up")
        t = np.arange(12000) / 24000
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 24000


ITEMS = [WordItem("greeting_001", "Hello"), WordItem("greeting_002", "Goodbye"), WordItem("greeting_004", "Thanks")]
DAY = dt.date(2026, 11, 2)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "data" / "audio", tmp_path / "data" / "audio_manifest.json", tmp_path


def run(paths, items=ITEMS, backend=None):
    out, manifest, root = paths
    return generate(items, out, manifest, backend or FakeBackend(), repo_root=root, today=DAY)


def test_creates_labelled_files_and_manifest(paths):
    out, manifest, _ = paths
    r = run(paths)
    assert r.created == ["greeting_001", "greeting_002", "greeting_004"] and not r.failed
    assert sorted(p.name for p in out.glob("*.mp3")) == [
        "greeting_001_en_tts_placeholder.mp3", "greeting_002_en_tts_placeholder.mp3",
        "greeting_004_en_tts_placeholder.mp3"]
    e = {x["word_id"]: x for x in json.loads(manifest.read_text())["entries"]}
    assert e["greeting_001"] == {
        "word_id": "greeting_001", "path": "data/audio/greeting_001_en_tts_placeholder.mp3",
        "kind": "tts_placeholder", "validated": False, "language": "en", "text": "Hello",
        "engine": "fake", "voice": "fake_voice", "license": "test only", "date": "2026-11-02"}


def test_output_is_a_playable_mp3(paths):
    run(paths)
    with av.open(str(paths[0] / f"greeting_001{SUFFIX}")) as c:
        assert c.streams.audio[0].codec_context.name in {"mp3", "mp3float"}
        assert sum(f.samples for f in c.decode(audio=0)) > 1000


def test_idempotent_second_run_skips_everything(paths):
    run(paths)
    out, manifest, _ = paths
    before = {p.name: p.read_bytes() for p in out.glob("*.mp3")}, manifest.read_text()
    b = FakeBackend()
    r = run(paths, backend=b)
    assert r.created == [] and len(r.skipped) == 3 and b.heard == []
    assert ({p.name: p.read_bytes() for p in out.glob("*.mp3")}, manifest.read_text()) == before


def test_never_overwrites_an_existing_file(paths):
    out, _, _ = paths
    out.mkdir(parents=True)
    (out / f"greeting_001{SUFFIX}").write_bytes(b"precious")
    r = run(paths)
    assert (out / f"greeting_001{SUFFIX}").read_bytes() == b"precious"
    assert r.skipped == ["greeting_001"] and r.warnings  # not in manifest: warned, not claimed


def test_native_speaker_entries_and_files_are_untouched(paths):
    out, manifest, _ = paths
    out.mkdir(parents=True)
    native = {"word_id": "greeting_001", "path": "data/audio/greeting_001_native.mp3",
              "kind": "native_speaker", "validated": True}
    manifest.write_text(json.dumps({"schema_version": "draft-1", "entries": [native]}))
    (out / "greeting_001_native.mp3").write_bytes(b"native")
    run(paths)
    kinds = [(e["word_id"], e["kind"]) for e in json.loads(manifest.read_text())["entries"]]
    assert ("greeting_001", "native_speaker") in kinds and ("greeting_001", "tts_placeholder") in kinds
    assert native in json.loads(manifest.read_text())["entries"]
    assert (out / "greeting_001_native.mp3").read_bytes() == b"native"


def test_one_failure_does_not_stop_the_batch(paths):
    r = run(paths, backend=FakeBackend(fail_on=["Goodbye"]))
    assert r.created == ["greeting_001", "greeting_004"]
    assert r.failed == [("greeting_002", "RuntimeError: engine blew up")]
    assert not (paths[0] / f"greeting_002{SUFFIX}").exists()


def test_unsafe_ids_are_rejected(paths):
    r = run(paths, items=[WordItem("../evil", "Hello"), WordItem("a/b", "Hi")])
    assert r.created == [] and len(r.failed) == 2 and not list(paths[2].rglob("*.mp3"))


def test_only_english_text_is_sent_to_the_engine(paths):
    lex = paths[2] / "lex.json"
    lex.write_text(json.dumps({"entries": [{
        "id": "greeting_001", "rohingya_text": "sólam",
        "english_meaning": {"word": "Hello"}, "example_sentence": {"rohingya": "Salaam alaikum!"}}]}))
    b = FakeBackend()
    run(paths, items=load_words(lex), backend=b)
    assert b.heard == ["Hello"]


def test_load_words_reads_both_lexicon_shapes_and_never_writes(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"entries": [{"id": "g1", "english_meaning": {"word": "Hello"}}, {"id": "bad"}]}))
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"entries": [{"id": "word_001", "english": "Doctor"}]}))
    before = a.read_text()
    assert load_words(a) == [WordItem("g1", "Hello")]
    assert load_words(b) == [WordItem("word_001", "Doctor")]
    assert a.read_text() == before


def test_select_words_hero_limit_and_unknown():
    words = [WordItem(f"greeting_{i:03d}", f"w{i}") for i in range(1, 31)]
    hero, unknown = select_words(words, ids=list(HERO_IDS))
    assert [w.word_id for w in hero] == list(HERO_IDS) and unknown == []
    assert len(select_words(words, limit=5)[0]) == 5
    assert select_words(words, ids=["nope"]) == ([], ["nope"])


def test_backend_registry_is_pluggable():
    register_backend("fake", lambda **o: FakeBackend())
    assert "fake" in available_backends() and "kokoro" in available_backends()
    assert get_backend("fake").name == "fake"
    with pytest.raises(ValueError):
        get_backend("elevenlabs-not-installed")


def test_to_mp3_clips_out_of_range_samples():
    assert len(to_mp3(np.array([2.0, -2.0] * 6000, dtype=np.float32), 24000)) > 0
