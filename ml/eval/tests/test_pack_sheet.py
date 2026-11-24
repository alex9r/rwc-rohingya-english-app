"""Pack and ingest tests. The shard and the filled sheet are made up for the test."""

import io
import json
import tarfile

import pytest

from ml.eval import manifest, pack, sheet


def _shard(path, broadcasts=3, per=9):
    """A fake WebDataset shard: each clip has a .json sidecar and a tiny .mp3."""
    n = 0
    with tarfile.open(path, "w") as t:
        for b in range(broadcasts):
            url = f"https://example.org/vba/2022/10/{b + 1:02d}/prog.mp3"
            for k in range(per):
                n += 1
                dur = 3.0 if k == 6 else 8.0  # one too-short clip per broadcast
                meta = json.dumps({"file_name": f"{n:06d}.mp3", "duration": dur, "download_url": url}).encode()
                for name, data in ((f"{n:06d}.json", meta), (f"{n:06d}.mp3", b"mp3-%d" % n)):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    t.addfile(info, io.BytesIO(data))
    return path


def test_select_rules(tmp_path):
    shard = _shard(tmp_path / "s.tar")
    picks = pack.select(shard, n=100, per_broadcast=2, skip_first=5)
    assert len(picks) == 6                                  # 3 broadcasts x 2
    assert all(5 <= c["duration"] <= 12 for c in picks)     # the 3 s clip is never picked
    assert pack.select(shard, per_broadcast=2) == pack.select(shard, per_broadcast=2)  # seeded


def test_select_skips_each_broadcasts_opening(tmp_path):
    shard = _shard(tmp_path / "s.tar", broadcasts=2, per=9)
    picks = pack.select(shard, n=100, per_broadcast=9, skip_first=5)
    # broadcast 1 holds clips 1..9, broadcast 2 holds 10..18; openings are 1..5 and 10..14
    assert not {c["n"] for c in picks} & {1, 2, 3, 4, 5, 10, 11, 12, 13, 14}


def test_build_writes_audio_sheet_and_private_map(tmp_path):
    shard = _shard(tmp_path / "s.tar")
    out = tmp_path / "pack"
    info = pack.build(shard, out, n=4, per_broadcast=2)
    assert info["clips"] == 4
    assert sorted(p.name for p in (out / "audio").iterdir()) == [f"voa_{i:03d}.mp3" for i in range(1, 5)]
    assert (out / "_private_source_map.csv").read_text().count("example.org") == 4
    assert (out / "transcription_sheet.xlsx").exists() or (out / "transcription_sheet.csv").exists()
    # Nothing that names the source ends up in the sheet the transcriber sees.
    sheet_text = (out / "transcription_sheet.csv").read_text() if (out / "transcription_sheet.csv").exists() else ""
    assert "example.org" not in sheet_text


def _filled_csv(tmp_path, rows):
    audio = tmp_path / "audio"
    audio.mkdir()
    for i in range(1, 6):
        (audio / f"voa_{i:03d}.mp3").write_bytes(b"x")
    p = tmp_path / "sheet.csv"
    p.write_text("clip_id,audio_file,Transcript (Latin Rohingyalish),Unusable? (reason),"
                 "Unsure about a word?,Notes,Your ID (e.g. T01)\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p, audio


def test_ingest_keeps_only_completed_rows(tmp_path):
    p, audio = _filled_csv(tmp_path, [
        "voa_001,voa_001.mp3,Iiba ki tua*r noya,no,no,,T01",
        "voa_002,voa_002.mp3,,music,,,T01",              # unusable
        "voa_003,voa_003.mp3,,,,,",                      # not done yet
        "voa_004,voa_004.mp3,aa*i dhath'tha [?],,yes,,T01",
    ])
    out = tmp_path / "m.jsonl"
    info = sheet.ingest(p, audio, out)
    assert info == {"clips": 2, "unusable": 1, "blank": 1, "unsure": 1, "transcribers": ["T01"]}
    clips = manifest.load(out)                           # the manifest passes the framework's validator
    assert [c.clip_id for c in clips] == ["voa_001", "voa_004"]
    assert clips[0].language == "rhg" and clips[0].verified_by == "T01"
    assert clips[1].meta["unsure"] is True


def test_ingest_reports_every_problem(tmp_path):
    p, audio = _filled_csv(tmp_path, [
        "voa_001,voa_001.mp3,some words,,,,",            # no transcriber ID
        "voa_002,voa_002.mp3,some words,music,,,T01",    # transcript but marked unusable
        "voa_099,voa_099.mp3,some words,,,,T01",         # audio missing
    ])
    with pytest.raises(sheet.SheetError) as e:
        sheet.ingest(p, audio, tmp_path / "m.jsonl")
    msg = str(e.value)
    assert "no transcriber ID" in msg and "marked unusable" in msg and "audio not found" in msg


def test_ingest_refuses_an_empty_sheet(tmp_path):
    p, audio = _filled_csv(tmp_path, ["voa_001,voa_001.mp3,,,,,"])
    with pytest.raises(sheet.SheetError, match="no completed rows"):
        sheet.ingest(p, audio, tmp_path / "m.jsonl")


def test_ingest_reads_the_xlsx_the_pack_writes(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    shard = _shard(tmp_path / "s.tar")
    out = tmp_path / "pack"
    pack.build(shard, out, n=3, per_broadcast=1)
    xlsx = out / "transcription_sheet.xlsx"
    wb = openpyxl.load_workbook(xlsx)
    ws = wb["Transcripts"]
    ws["C2"], ws["G2"] = "Adam-e aa*re hoilde", "T01"     # fill one row like a transcriber would
    ws["D3"], ws["G3"] = "English", "T01"
    wb.save(xlsx)
    info = sheet.ingest(xlsx, out / "audio", tmp_path / "m.jsonl", out / "_private_source_map.csv")
    assert info["clips"] == 1 and info["unusable"] == 1
    row = json.loads((tmp_path / "m.jsonl").read_text().splitlines()[0])
    assert row["reference"] == "Adam-e aa*re hoilde" and row["broadcast_date"]
