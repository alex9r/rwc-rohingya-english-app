"""Build the transcription pack: VOA clips plus a sheet for a Rohingya speaker to fill in.

The VOA corpus (`freococo/rohingya_asr_audio`) has no transcripts. This picks a small,
reproducible set of clips, copies them out of a WebDataset shard, and writes a sheet.

Selection (defaults match the pack sent to the Welcome Centre on shard 0):
  - skip the first 5 clips of each broadcast (the opening has an English station ident)
  - keep clips of 5 to 12 s
  - at most 4 clips per broadcast, spread across broadcast dates
  - fixed seed, so anyone re-running gets the same clips

Outputs, all outside git:
  audio/voa_NNN.mp3             the clips, renamed so the file name says nothing about source
  transcription_sheet.xlsx      (or .csv if openpyxl is not installed)
  _private_source_map.csv       clip_id -> shard file, broadcast date, duration, source URL.
                                Keep it; do not send it to the transcriber.
"""

from __future__ import annotations

import csv
import json
import random
import re
import tarfile
from collections import defaultdict
from pathlib import Path

HEADERS = [
    "clip_id", "audio_file", "Transcript (Latin Rohingyalish)", "Unusable? (reason)",
    "Unsure about a word?", "Notes", "Your ID (e.g. T01)",
]
UNUSABLE_CHOICES = "no,music,English,unclear,other"

INSTRUCTIONS = [
    ("Transcribing Rohingya audio clips", True),
    ("Thank you for helping. Open each audio file in the 'audio' folder, listen, and write what is said "
     "in the Transcripts tab.", False),
    ("", False),
    ("What to write", True),
    ("1. Write the words in Latin letters (Rohingyalish), using the spelling you normally use. "
     "Do not translate. Write what is said, not what it means.", False),
    ("2. Put the clip's words in column C. Punctuation is optional. Do not add words you did not hear.", False),
    ("3. If a clip is music, English, too unclear, or you would rather not listen to it, choose a reason "
     "in column D and leave column C empty.", False),
    ("4. If you are unsure about a word, write your best guess and choose 'yes' in column E. "
     "You can also write [?] next to the word.", False),
    ("5. Use column F for anything else, such as a spelling you were unsure about.", False),
    ("6. Type your ID (for example T01) in column G on each row you finish. Use an ID, not your name.", False),
    ("", False),
    ("Please also tell us", True),
    ("Any spelling conventions you followed, such as how you write particular sounds. A few lines is "
     "enough. Put it in the 'Spelling notes' tab.", False),
    ("", False),
    ("Some clips may be news about conflict. Skip any clip you would rather not listen to. "
     "You can stop at any time.", False),
    ("", False),
    ("Example of the format (from a published Rohingya sentence list, not one of the clips):", True),
    ("Iiba ki tua*r noya fua*jja ne?", False),
]


def select(shard: Path, *, n: int = 80, per_broadcast: int = 4, skip_first: int = 5,
           min_s: float = 5.0, max_s: float = 12.0, seed: int = 11) -> list[dict]:
    """Return the chosen clips (metadata only) from one WebDataset shard."""
    by_broadcast: dict[str, list[dict]] = defaultdict(list)
    with tarfile.open(shard) as t:
        for m in t.getmembers():
            if re.fullmatch(r"\d+\.json", m.name):
                d = json.load(t.extractfile(m))
                d["n"] = int(m.name[:-5])
                by_broadcast[d["download_url"]].append(d)
    rng = random.Random(seed)
    picks: list[dict] = []
    for url, clips in sorted(by_broadcast.items()):
        clips.sort(key=lambda d: d["n"])
        pool = [c for c in clips[skip_first:] if min_s <= c["duration"] <= max_s]
        rng.shuffle(pool)
        date = re.search(r"/(\d{4}/\d{2}/\d{2})/", url)
        for c in pool[:per_broadcast]:
            picks.append({**c, "date": date.group(1) if date else ""})
    rng.shuffle(picks)
    return picks[:n]


def write_sheet(out: Path, n: int) -> Path:
    """Write the transcriber-facing sheet. xlsx if openpyxl is available, otherwise csv."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError:
        path = out / "transcription_sheet.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(HEADERS)
            for i in range(1, n + 1):
                w.writerow([f"voa_{i:03d}", f"voa_{i:03d}.mp3", "", "", "", "", ""])
        return path

    wb = Workbook()
    ins = wb.active
    ins.title = "Instructions"
    for i, (text, bold) in enumerate(INSTRUCTIONS, 1):
        c = ins.cell(row=i, column=1, value=text)
        c.font = Font(bold=bold)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ins.column_dimensions["A"].width = 110

    ws = wb.create_sheet("Transcripts")
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDE6F0")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i in range(1, n + 1):
        ws.append([f"voa_{i:03d}", f"voa_{i:03d}.mp3", "", "", "", "", ""])
    for col, w in zip("ABCDEFG", (10, 14, 70, 20, 16, 40, 16)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    dv1 = DataValidation(type="list", formula1=f'"{UNUSABLE_CHOICES}"', allow_blank=True)
    dv1.add(f"D2:D{n + 1}")
    dv2 = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    dv2.add(f"E2:E{n + 1}")
    ws.add_data_validation(dv1)
    ws.add_data_validation(dv2)
    ws.freeze_panes = "C2"

    sn = wb.create_sheet("Spelling notes")
    sn["A1"] = "Spelling conventions you followed (free text):"
    sn["A1"].font = Font(bold=True)
    sn.column_dimensions["A"].width = 110
    path = out / "transcription_sheet.xlsx"
    wb.save(path)
    return path


def build(shard: str | Path, out: str | Path, **kw) -> dict:
    shard, out = Path(shard), Path(out)
    picks = select(shard, **kw)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    with tarfile.open(shard) as t, open(out / "_private_source_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "shard_file", "broadcast_date", "duration_s", "source_url"])
        for i, c in enumerate(picks, 1):
            cid = f"voa_{i:03d}"
            (out / "audio" / f"{cid}.mp3").write_bytes(t.extractfile(c["file_name"]).read())
            w.writerow([cid, c["file_name"], c["date"], c["duration"], c["download_url"]])
    sheet = write_sheet(out, len(picks))
    return {"clips": len(picks), "broadcast_dates": len({c["date"] for c in picks}),
            "seconds": round(sum(c["duration"] for c in picks)), "sheet": str(sheet)}
