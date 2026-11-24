"""Turn a filled-in transcription sheet into an evaluation manifest.

Reads the Transcripts tab of the .xlsx (or a .csv export) made by `pack.py`. A row is
kept when it has a transcript, is not marked unusable, and has a transcriber ID.

One transcriber per clip means these references are transcribed by a native speaker, not
double-checked. `verified_by` holds the transcriber's pseudonymous ID. If a second person
checks a subset, add that agreement as a separate measure rather than editing this.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


class SheetError(ValueError):
    pass


def _rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [dict(r) for r in csv.DictReader(f)]
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise SheetError("reading .xlsx needs openpyxl (pip install openpyxl), or export the tab as csv") from e
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["Transcripts"] if "Transcripts" in wb.sheetnames else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(it)]
    return [{h: ("" if v is None else str(v)) for h, v in zip(header, row)} for row in it]


def _col(row: dict[str, str], *prefixes: str) -> str:
    for key, val in row.items():
        k = key.strip().lower()
        if any(k.startswith(p) for p in prefixes):
            return (val or "").strip()
    return ""


def ingest(sheet: str | Path, audio_dir: str | Path, out: str | Path,
           source_map: str | Path | None = None) -> dict[str, Any]:
    """Write a manifest (JSONL) and return counts. Raises SheetError listing every problem."""
    sheet, audio_dir, out = Path(sheet), Path(audio_dir), Path(out)
    meta: dict[str, dict[str, str]] = {}
    if source_map:
        with open(source_map, newline="", encoding="utf-8") as f:
            meta = {r["clip_id"]: r for r in csv.DictReader(f)}

    problems: list[str] = []
    kept: list[dict[str, Any]] = []
    skipped = {"blank": 0, "unusable": 0}
    for r in _rows(sheet):
        cid = _col(r, "clip_id")
        if not cid:
            continue
        text = _col(r, "transcript")
        reason = _col(r, "unusable").lower()
        if reason not in ("", "no"):
            skipped["unusable"] += 1
            if text:
                problems.append(f"{cid}: has a transcript but is marked unusable ({reason}); decide which")
            continue
        if not text:
            skipped["blank"] += 1
            continue
        who = _col(r, "your id", "transcriber")
        if not who:
            problems.append(f"{cid}: transcript but no transcriber ID")
            continue
        audio = audio_dir / (_col(r, "audio_file") or f"{cid}.mp3")
        if not audio.is_file():
            problems.append(f"{cid}: audio not found: {audio}")
            continue
        row: dict[str, Any] = {
            "clip_id": cid,
            "audio": os.path.relpath(audio.resolve(), out.resolve().parent),
            "reference": text,
            "language": "rhg",
            "speaker_id": "voa_broadcast",   # speakers are unknown; one label, no speaker analysis
            "verified_by": who,
            "source": "voa",
            "unsure": _col(r, "unsure").lower() == "yes" or "[?]" in text,
        }
        if cid in meta:
            row["broadcast_date"] = meta[cid].get("broadcast_date", "")
            row["duration_s"] = meta[cid].get("duration_s", "")
        kept.append(row)
    if problems:
        raise SheetError(f"{sheet.name}: {len(problems)} problem(s)\n  " + "\n  ".join(problems))
    if not kept:
        raise SheetError(f"{sheet.name}: no completed rows")
    with open(out, "w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"clips": len(kept), "unusable": skipped["unusable"], "blank": skipped["blank"],
            "unsure": sum(r["unsure"] for r in kept), "transcribers": sorted({r["verified_by"] for r in kept})}
