"""Logic tests. Hypotheses here are hand-written to exercise the metrics; they are NOT model output."""

import json

import pytest

from ml.eval import manifest, prompts, runner
from ml.eval.metrics import (CORRECT, EXTRA, INCORRECT, MISSING, MIXED, NO_OUTPUT,
                             SCRIPT_MISMATCH, breakdown, score_clip, summarize)
from ml.eval.text import align, detect_script, normalize

REF = "Jacobottu baseballot mon no'aish'shil."


def test_normalize_keeps_orthography_marks_by_default():
    assert normalize("Adam-e aa*re hoilde, Alice-ottu!") == ["adam-e", "aa*re", "hoilde", "alice-ottu"]
    assert normalize("mon no’aish’shil") == ["mon", "no'aish'shil"]  # curly -> straight


def test_fold_marks_is_lenient():
    assert normalize("Adam-e aa*re no'aish", fold_marks=True) == ["adam", "e", "aare", "noaish"]


def test_exact_match():
    s = score_clip("c", REF, "jacobottu baseballot mon no'aish'shil")
    assert s.verdict == CORRECT and s.wer == 0.0 and s.cer == 0.0


def test_missing_word():
    s = score_clip("c", REF, "jacobottu baseballot no'aish'shil")
    assert (s.verdict, s.dels, s.subs, s.ins) == (MISSING, 1, 0, 0)
    assert s.missing == ["mon"] and s.wer == pytest.approx(0.25)


def test_incorrect_word():
    s = score_clip("c", REF, "jacobottu baseballot mon noaish")
    assert (s.verdict, s.subs) == (INCORRECT, 1)
    assert s.substitutions == [("no'aish'shil", "noaish")]


def test_extra_word():
    s = score_clip("c", REF, "jacobottu baseballot mon no'aish'shil ne")
    assert (s.verdict, s.ins, s.insertions) == (EXTRA, 1, ["ne"])


def test_mixed():
    s = score_clip("c", REF, "jacob baseballot no'aish'shil")
    assert s.verdict == MIXED and (s.subs, s.dels) == (1, 1)


def test_no_output_counts_all_words_missing():
    s = score_clip("c", REF, "")
    assert s.verdict == NO_OUTPUT and s.dels == 4 and s.wer == 1.0


def test_script_mismatch_is_not_scored():
    s = score_clip("c", REF, "জ্যাকব বেসবল")
    assert detect_script(REF) == "LATIN" and detect_script("জ্যাকব") == "BENGALI"
    assert s.verdict == SCRIPT_MISMATCH and s.wer is None
    agg = summarize([s, score_clip("d", REF, REF)])
    assert agg["clips_scored"] == 1 and agg["clips_script_mismatch"] == 1 and agg["wer"] == 0.0


def test_alignment_is_minimal_and_deterministic():
    assert [o.kind for o in align(["a", "b", "c"], ["a", "c"])] == ["equal", "del", "equal"]
    # Equal-cost alternatives exist here (2 edits either way); ties prefer substitution.
    assert [o.kind for o in align(["a", "b", "c"], ["a", "c", "d"])] == ["equal", "sub", "sub"]


def test_summary_is_micro_averaged_and_breaks_down_by_field():
    a = score_clip("a", "one two three four", "one two three four", meta={"noise": "quiet"})
    b = score_clip("b", "one two", "one", meta={"noise": "noisy"})
    agg = summarize([a, b])
    assert agg["wer"] == pytest.approx(1 / 6)  # 1 error / 6 words, not mean of 0 and 0.5
    by = breakdown([a, b], "noise")
    assert by["quiet"]["wer"] == 0.0 and by["noisy"]["wer"] == 0.5
    assert agg["most_missed_words"] == [("two", 1)]


def _write_manifest(tmp_path, rows):
    (tmp_path / "a.wav").write_bytes(b"x")
    m = tmp_path / "m.jsonl"
    m.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return m


def _row(**kw):
    return {"clip_id": "c1", "audio": "a.wav", "reference": REF, "language": "rhg",
            "speaker_id": "spk_001", "verified_by": "rev_1", **kw}


def test_manifest_loads(tmp_path):
    clips = manifest.load(_write_manifest(tmp_path, [_row(noise="quiet")]))
    assert clips[0].verified and clips[0].meta == {"noise": "quiet"}


def test_manifest_reports_every_problem(tmp_path):
    rows = [_row(), _row(), _row(clip_id="c2", language="xx"), _row(clip_id="c3", name="Someone"),
            _row(clip_id="c4", verified_by=""), _row(clip_id="c5", audio="gone.wav")]
    with pytest.raises(manifest.ManifestError) as e:
        manifest.load(_write_manifest(tmp_path, rows))
    msg = str(e.value)
    for needle in ("duplicate", "language must be", "personal-data", "no verified_by", "audio not found"):
        assert needle in msg


def test_unverified_allowed_only_on_request(tmp_path):
    m = _write_manifest(tmp_path, [_row(verified_by="")])
    with pytest.raises(manifest.ManifestError):
        manifest.load(m)
    assert not manifest.load(m, allow_unverified=True)[0].verified


def test_evaluate_with_fake_transcriber(tmp_path):
    clips = manifest.load(_write_manifest(tmp_path, [_row(noise="noisy")]))
    fake = {"ok": (REF, "ok")}
    rep = runner.evaluate(clips, lambda p, lang: fake["ok"], asr_language="bn")
    assert rep["overall"]["wer"] == 0.0 and rep["breakdown"]["noise"]["noisy"]["clips"] == 1
    failed = runner.evaluate(clips, lambda p, lang: ("", "no_speech"), asr_language="bn")
    assert failed["overall"]["wer"] == 1.0 and failed["transcriber_failures"] == {"c1": "no_speech"}
    assert "`bn`" in runner.to_markdown(failed)


def test_prompts_draws_from_kit_without_touching_it(tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "kit5k.tsv").write_text("eng\trhg\nHi.\tSalam o\nLong one.\ta b c d e f g h i j\nOk.\tIiba ki\n", encoding="utf-8")
    (kit / "core_kit5k.tsv").write_text("id\ttext\n1\tHi.\n2\tLong one.\n3\tOk.\n", encoding="utf-8")
    before = (kit / "kit5k.tsv").read_bytes()
    out = tmp_path / "p.jsonl"
    assert prompts.build(kit, out, n=10, max_words=8) == 2  # the 10-word sentence is excluded
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert {r["source_id"] for r in rows} == {"tatoeba:1", "tatoeba:3"}
    assert all(r["audio"] == "" and r["speaker_id"] == "" and r["verified_by"] == "" for r in rows)
    assert (kit / "kit5k.tsv").read_bytes() == before
