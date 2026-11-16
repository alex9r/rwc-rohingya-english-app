"""Tests for calibrating thresholds from Luna's ml.eval report, and for setting them
through the environment. No model: a fake scorer stands in for transcribe()."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ml.speech.calibrate import CalibrationError, clips_from_eval, main

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
