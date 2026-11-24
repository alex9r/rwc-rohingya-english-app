"""Tests for calibrating thresholds from Luna's ml.eval report and from the review queue,
and for setting them through the environment. No model: a fake scorer or fake Whisper
stands in for transcribe()."""

import io
import json
import math
import os
import subprocess
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ml.speech import transcribe
from ml.speech.calibrate import CalibrationError, clips_from_eval, clips_from_queue, main
from ml.speech.review import ReviewQueue
from ml.speech.transcribe import SAMPLE_RATE

REPO = Path(__file__).resolve().parents[3]


def write_eval(tmp_path, clips, failures=None, language="bn"):
    """A manifest and an ml.eval-shaped report for these (clip_id, wer) pairs."""
    (tmp_path / "audio").mkdir()
    lines = []
    for cid, _ in clips:
        (tmp_path / "audio" / f"{cid}.wav").write_bytes(b"x")
        lines.append(json.dumps({"clip_id": cid, "audio": f"audio/{cid}.wav", "reference": "r",
                                 "language": "rhg", "speaker_id": "S1", "verified_by": "R1"}))
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {
        "asr_language": language,
        "transcriber_failures": failures or {},
        "clips": [{"clip_id": cid, "wer": wer} for cid, wer in clips],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report, report_path, manifest


def scorer_from(confidences, seen=None):
    """Fake transcribe(): clip_id -> confidence, or -> (status, confidence) for a failure."""
    def run(path, language):
        if seen is not None:
            seen.append(language)
        value = confidences[path.stem]
        return value if isinstance(value, tuple) else ("ok", value)
    return run


def test_pairs_wer_with_confidence_and_uses_the_reports_proxy_language(tmp_path):
    report, _, manifest = write_eval(tmp_path, [("a", 0.0), ("b", 0.8)], language="ur")
    seen = []
    clips, skipped = clips_from_eval(report, manifest, scorer_from({"a": 0.9, "b": 0.3}, seen))
    assert sorted(clips) == [(0.3, 0.8), (0.9, 0.0)]
    assert seen == ["ur", "ur"] and not any(skipped.values())


def test_leaves_out_clips_that_say_nothing_about_confidence(tmp_path):
    report, _, manifest = write_eval(
        tmp_path, [("ok1", 0.1), ("mismatch", None), ("failed", 1.0), ("now_bad", 0.5)],
        failures={"failed": "no_speech"},
    )
    report["clips"].append({"clip_id": "ghost", "wer": 0.2})  # not in the manifest
    scorer = scorer_from({"ok1": 0.9, "now_bad": ("no_speech", 0.0)})
    clips, skipped = clips_from_eval(report, manifest, scorer)
    assert clips == [(0.9, 0.1)]
    assert skipped == {"no_wer": 1, "failed_in_eval": 1, "not_in_manifest": 1, "not_ok_now": 1}


def test_bad_manifest_line_is_reported(tmp_path):
    report, _, manifest = write_eval(tmp_path, [("a", 0.0)])
    manifest.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(CalibrationError, match="line 1"):
        clips_from_eval(report, manifest, scorer_from({}))


def test_cli_recommends_thresholds_from_an_eval_report(tmp_path, capsys):
    pairs = [(f"c{i}", 0.0) for i in range(10)] + [(f"m{i}", 0.2) for i in range(10)] \
        + [(f"p{i}", 0.9) for i in range(10)]
    confidences = {cid: {"c": 0.9, "m": 0.7, "p": 0.3}[cid[0]] for cid, _ in pairs}
    _, report, manifest = write_eval(tmp_path, pairs)
    code = main(["--report", str(report), "--manifest", str(manifest), "--accept-wer", "0.05"],
                scorer=scorer_from(confidences))
    out = capsys.readouterr().out
    assert code == 0
    assert "recommended HIGH_CONFIDENCE: 0.75" in out and "recommended LOW_CONFIDENCE:  0.4" in out
    assert "RWC_HIGH_CONFIDENCE=0.75 RWC_LOW_CONFIDENCE=0.4" in out


def test_cli_rejects_mixed_inputs(tmp_path):
    _, report, manifest = write_eval(tmp_path, [("a", 0.0)])
    with pytest.raises(SystemExit):
        main(["--report", str(report)], scorer=scorer_from({}))


def test_cli_needs_at_least_one_source():
    with pytest.raises(SystemExit):
        main([])


# --------------------------------------------------------------------------- review queue


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


AUDIO = wav_bytes()


class FakeWhisper:
    """One segment with this text at this confidence."""

    def __init__(self, text, confidence):
        self.text, self.confidence = text, confidence

    def transcribe(self, audio, **kwargs):
        s = SimpleNamespace(start=0.0, end=1.0, text=self.text, avg_logprob=math.log(self.confidence),
                            no_speech_prob=0.0, compression_ratio=1.2)
        return iter([s]), SimpleNamespace(language="bn", language_probability=0.6)


def queue_with(tmp_path, clips):
    """A review queue of (heard, confidence, reviewer's transcript, model) clips.
    A transcript of None leaves the clip unreviewed; "REJECT" rejects it."""
    q = ReviewQueue(tmp_path / "queue")
    for heard, confidence, reference, model in clips:
        r = transcribe(AUDIO, "bn", model=FakeWhisper(heard, confidence))
        cid = q.save(AUDIO, r, speaker_id="S1", consent_version="v1", consent_uses=["scorer_evaluation"],
                     model=model, ext="wav", force=True)
        if reference == "REJECT":
            q.reject(cid, "R1")
        elif reference is not None:
            q.verify(cid, reference, "R1")
    return q.root


def test_reviewed_queue_clips_are_scored_against_the_reviewers_transcript(tmp_path):
    root = queue_with(tmp_path, [
        ("ami dactor sai", 0.3, "ami dactor sai", "small"),   # heard right: WER 0
        ("ami dactor", 0.2, "ami dactor sai", "small"),       # one word missing: WER 1/3
        ("ami dactor sai", 0.4, "ami dactor sai", None),      # model not recorded: kept
        ("ami", 0.25, None, "small"),                         # not reviewed yet
        ("noise", 0.1, "REJECT", "small"),                    # rejected
        ("ami dactor sai", 0.3, "ami dactor sai", "medium"),  # thresholds don't carry over
        ("আমি ডাক্তার চাই", 0.3, "ami dactor sai", "small"),  # Bengali script: no WER
    ])
    clips, skipped = clips_from_queue(root, "small")
    assert sorted((round(c, 2), round(w, 2)) for c, w in clips) == [(0.2, 0.33), (0.3, 0.0), (0.4, 0.0)]
    assert skipped == {"not_reviewed": 1, "rejected": 1, "other_model": 1, "no_wer": 1}


def test_missing_queue_is_an_error(tmp_path):
    with pytest.raises(CalibrationError, match="no review queue"):
        clips_from_queue(tmp_path / "nope", "small")


def test_cli_pools_sources_and_counts_repeats_users_did_not_need(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys.modules["ml.speech.transcribe"], "LOW_CONFIDENCE", 0.5)  # not the env's
    rows = [(0.9, 0.0)] * 10 + [(0.6, 0.4)] * 10 + [(0.45, 0.0)] * 10 + [(0.3, 0.8)] * 10
    results = tmp_path / "results.csv"
    results.write_text("confidence,wer\n" + "".join(f"{c},{w}\n" for c, w in rows), encoding="utf-8")
    root = queue_with(tmp_path, [("ami dactor", 0.2, "ami dactor sai", "small")])

    code = main([str(results), "--queue", str(root), "--model", "small"])
    out = capsys.readouterr().out
    assert code == 0
    assert "1 reviewed clips" in out and "41 clips with WER" in out
    assert "recommended HIGH_CONFIDENCE: 0.65" in out and "recommended LOW_CONFIDENCE:  0.4" in out
    # at 0.50 the ten clips at 0.45 are asked again although they were heard right
    assert "current     LOW 0.50: asks to repeat 21 clips, 10 of them heard right anyway" in out
    assert "recommended LOW 0.40: asks to repeat 11 clips, 0 of them heard right anyway" in out


# --------------------------------------------------------------------------- thresholds from env


def thresholds_with(env):
    """Import ml.speech in a fresh interpreter with these variables set."""
    code = "from ml.speech import HIGH_CONFIDENCE as h, LOW_CONFIDENCE as l; print(h, l)"
    full_env = {**os.environ, **env}
    return subprocess.run([sys.executable, "-c", code], cwd=REPO, env=full_env,
                          capture_output=True, text=True)


def test_thresholds_can_be_set_per_deployment():
    r = thresholds_with({"RWC_HIGH_CONFIDENCE": "0.8", "RWC_LOW_CONFIDENCE": "0.35"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["0.8", "0.35"]


@pytest.mark.parametrize("env", [
    {"RWC_LOW_CONFIDENCE": "high"},
    {"RWC_HIGH_CONFIDENCE": "1.5"},
    {"RWC_HIGH_CONFIDENCE": "0.4", "RWC_LOW_CONFIDENCE": "0.6"},
])
def test_bad_thresholds_fail_at_startup(env):
    r = thresholds_with(env)
    assert r.returncode != 0 and "RWC_" in r.stderr
