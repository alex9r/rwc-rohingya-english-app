"""Tests for ml.speech.review: which clips are kept, consent, the reviewer's decisions,
deletion, and the export to Luna's ml.eval manifest. Uses a fake model; runs offline."""

import io
import json
import math
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from ml.speech import HIGH_CONFIDENCE, LOW_CONFIDENCE, Status, transcribe
from ml.speech.review import ReviewError, ReviewQueue, main, needs_review
from ml.speech.transcribe import SAMPLE_RATE, TranscriptionResult

CONSENT = dict(speaker_id="S007", consent_version="v1", consent_uses=["scorer_evaluation"])


def wav_bytes(seconds: float = 1.5) -> bytes:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class FakeModel:
    def __init__(self, confidence):
        self.confidence = confidence

    def transcribe(self, audio, **kwargs):
        s = SimpleNamespace(start=0.0, end=1.0, text="ami dactor sai", avg_logprob=math.log(self.confidence),
                            no_speech_prob=0.0, compression_ratio=1.2)
        return iter([s]), SimpleNamespace(language="bn", language_probability=0.6)


def result_at(confidence, attempt=1):
    return transcribe(AUDIO, "bn", model=FakeModel(confidence), attempt=attempt)


AUDIO = wav_bytes()
LOW = LOW_CONFIDENCE - 0.1
MEDIUM = (LOW_CONFIDENCE + HIGH_CONFIDENCE) / 2
HIGH = min(HIGH_CONFIDENCE + 0.05, 1.0)


@pytest.fixture
def queue(tmp_path):
    return ReviewQueue(tmp_path / "queue")


# --------------------------------------------------------------------------- what gets kept


def test_only_low_confidence_needs_review():
    assert needs_review(result_at(LOW))
    assert not needs_review(result_at(MEDIUM))
    assert not needs_review(result_at(HIGH))
    assert not needs_review(TranscriptionResult(status=Status.NO_SPEECH))


def test_low_confidence_clip_is_saved_with_audio_and_record(queue):
    r = result_at(LOW, attempt=2)
    clip_id = queue.save(AUDIO, r, word_id="w_doctor", expected_text="I need a doctor",
                         model="small", ext="wav", **CONSENT)
    assert clip_id
    rec = queue.get(clip_id)
    assert queue.audio_path(clip_id).read_bytes() == AUDIO
    assert rec["status"] == "unvalidated" and rec["purpose"] == "research"
    assert rec["take"] == 2 and rec["word_id"] == "w_doctor"
    assert rec["storage_key"] == f"speech-review/{clip_id}.wav"
    assert rec["asr"]["text"] == "ami dactor sai" and rec["asr"]["confidence_level"] == "low"
    assert rec["asr"]["action"] == "ask_repeat" and rec["asr"]["reason"] == "low_confidence"
    assert rec["asr"]["thresholds"] == {"high": HIGH_CONFIDENCE, "low": LOW_CONFIDENCE}
    assert rec["reference"] is None and rec["verified_by"] is None


def test_confident_clips_are_not_saved(queue):
    assert queue.save(AUDIO, result_at(HIGH), **CONSENT) is None
    assert queue.save(AUDIO, result_at(MEDIUM), **CONSENT) is None
    assert queue.items() == []


def test_force_keeps_a_medium_clip_the_user_rejected(queue):
    assert queue.save(AUDIO, result_at(MEDIUM), force=True, **CONSENT)


def test_force_on_a_failed_clip_is_a_caller_error(queue):
    with pytest.raises(ReviewError, match="nothing to review"):
        queue.save(AUDIO, TranscriptionResult(status=Status.TOO_SHORT), force=True, **CONSENT)


def test_file_object_is_rewound_before_saving(queue):
    f = io.BytesIO(AUDIO)
    r = transcribe(f, "bn", model=FakeModel(LOW))  # reads the stream to the end
    clip_id = queue.save(f, r, **CONSENT)
    assert queue.audio_path(clip_id).read_bytes() == AUDIO
    assert queue.audio_path(clip_id).suffix == ".m4a"  # what the app records


def test_path_keeps_its_extension(queue, tmp_path):
    p = tmp_path / "clip.wav"
    p.write_bytes(AUDIO)
    clip_id = queue.save(p, result_at(LOW), **CONSENT)
    assert queue.audio_path(clip_id).suffix == ".wav"


# --------------------------------------------------------------------------- consent and identity


@pytest.mark.parametrize("uses", [[], ["reference_audio"], ["keep_after_project"]])
def test_no_research_consent_means_not_kept(queue, uses):
    assert queue.save(AUDIO, result_at(LOW), speaker_id="S007", consent_version="v1", consent_uses=uses) is None
    assert not queue.root.exists() or queue.items() == []


def test_model_training_consent_is_enough(queue):
    assert queue.save(AUDIO, result_at(LOW), speaker_id="S007", consent_version="v1",
                      consent_uses=["model_training"])


@pytest.mark.parametrize("bad", [
    dict(speaker_id="Jane Doe"),  # a name, not a pseudonymous ID
    dict(speaker_id="../etc"),
    dict(consent_version=""),
    dict(consent_uses=["scorer_evaluation", "marketing"]),
    dict(spoken_language="bn"),
])
def test_caller_mistakes_raise(queue, bad):
    with pytest.raises(ReviewError):
        queue.save(AUDIO, result_at(LOW), **{**CONSENT, **bad})


def test_clip_ids_cannot_escape_the_folder(queue):
    with pytest.raises(ReviewError, match="not a clip id"):
        queue.get("../../secrets")


# --------------------------------------------------------------------------- reviewing


def test_verify_records_the_reviewers_transcript(queue):
    clip_id = queue.save(AUDIO, result_at(LOW), **CONSENT)
    queue.verify(clip_id, "  ami daktor sai  ", "R01")
    rec = queue.get(clip_id)
    assert rec["status"] == "reviewed" and rec["reference"] == "ami daktor sai"
    assert rec["verified_by"] == "R01" and rec["reviewed_at"]
    assert [r["clip_id"] for r in queue.items("unvalidated")] == []


def test_a_decision_is_final(queue):
    clip_id = queue.save(AUDIO, result_at(LOW), **CONSENT)
    queue.reject(clip_id, "R01", note="not Rohingya")
    with pytest.raises(ReviewError, match="already rejected"):
        queue.verify(clip_id, "text", "R02")


@pytest.mark.parametrize("reference, reviewer", [("", "R01"), ("text", ""), ("text", "  ")])
def test_verify_needs_a_transcript_and_a_reviewer(queue, reference, reviewer):
    clip_id = queue.save(AUDIO, result_at(LOW), **CONSENT)
    with pytest.raises(ReviewError):
        queue.verify(clip_id, reference, reviewer)


# --------------------------------------------------------------------------- export and delete


def test_export_writes_reviewed_clips_as_an_eval_manifest(queue, tmp_path):
    keep = queue.save(AUDIO, result_at(LOW), word_id="w_doctor", **CONSENT)
    rejected = queue.save(AUDIO, result_at(LOW), **CONSENT)
    queue.save(AUDIO, result_at(LOW), **CONSENT)  # still waiting
    queue.verify(keep, "ami daktor sai", "R01")
    queue.reject(rejected, "R01")

    manifest = tmp_path / "eval" / "manifest.jsonl"
    assert queue.export_manifest(manifest) == 1
    (row,) = [json.loads(line) for line in manifest.read_text().splitlines()]
    # the fields ml.eval's manifest requires, nothing that identifies a person
    assert {k: row[k] for k in ("clip_id", "reference", "language", "speaker_id", "verified_by")} == {
        "clip_id": keep, "reference": "ami daktor sai", "language": "rhg",
        "speaker_id": "S007", "verified_by": "R01",
    }
    assert (manifest.parent / row["audio"]).resolve() == queue.audio_path(keep).resolve()
    assert row["word_id"] == "w_doctor"
    assert not {"name", "speaker_name", "email", "phone", "address"} & row.keys()


def test_delete_speaker_removes_their_clips_only(queue):
    mine = [queue.save(AUDIO, result_at(LOW), **CONSENT) for _ in range(2)]
    other = queue.save(AUDIO, result_at(LOW), **{**CONSENT, "speaker_id": "S008"})
    paths = [queue.audio_path(c) for c in mine]

    assert queue.delete_speaker("S007") == 2
    assert [r["clip_id"] for r in queue.items()] == [other]
    assert not any(p.exists() for p in paths)
    log = (queue.root / "deletions.log").read_text()
    assert '"clips_deleted": 2' in log and not any(c in log for c in mine)


def test_cli_list_verify_export(queue, tmp_path, capsys):
    clip_id = queue.save(AUDIO, result_at(LOW), expected_text="I need a doctor", **CONSENT)
    root = str(queue.root)
    assert main([root, "list"]) == 0
    assert clip_id in capsys.readouterr().out
    assert main([root, "verify", clip_id, "ami daktor sai", "--reviewer", "R01"]) == 0
    assert main([root, "export", str(tmp_path / "m.jsonl")]) == 0
    assert "wrote 1" in capsys.readouterr().out
    assert main([root, "verify", clip_id, "again", "--reviewer", "R01"]) == 2  # already decided


def test_cli_delete_previews_without_yes(queue, capsys):
    queue.save(AUDIO, result_at(LOW), **CONSENT)
    assert main([str(queue.root), "delete-speaker", "S007"]) == 0
    assert "Re-run with --yes" in capsys.readouterr().out
    assert len(queue.items()) == 1
    assert main([str(queue.root), "delete-speaker", "S007", "--yes"]) == 0
    assert queue.items() == []
