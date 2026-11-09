"""Fetch a small set of English clips from Tatoeba for the pronunciation smoke test.

Only clips whose audio licence is exactly "CC BY 4.0" are used (the export lists a
licence per clip). The audio is saved under --out (git-ignored); the manifest written
next to this script has no audio, just clip IDs, licence, attribution and target text.

    python -m ml.pronunciation.fetch_tatoeba_clips --out ml/pronunciation/smoke_clips

Network: downloads.tatoeba.org (two export files, ~15 MB) and tatoeba.org/audio/download/<id>
(one small mp3 per clip, fetched one at a time with a pause).
"""

from __future__ import annotations

import argparse
import bz2
import csv
import random
import re
import time
import urllib.request
from pathlib import Path

EXPORTS = "https://downloads.tatoeba.org/exports"
AUDIO_URL = "https://tatoeba.org/audio/download/{audio_id}"
LICENSE = "CC BY 4.0"
MANIFEST = Path(__file__).with_name("smoke_manifest.csv")
FIELDS = ["clip_id", "file", "source", "source_url", "license", "attribution", "target_text", "accent_label"]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "rwc-pronunciation-smoke-test (WAT.ai)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def pick(work: Path, n: int, per_speaker: int, seed: int) -> list[dict]:
    work.mkdir(parents=True, exist_ok=True)
    eng_path = work / "eng_sentences.tsv"
    audio_path = work / "sentences_with_audio.csv"
    if not eng_path.exists():
        eng_path.write_bytes(bz2.decompress(_get(f"{EXPORTS}/per_language/eng/eng_sentences.tsv.bz2")))
    if not audio_path.exists():
        import io
        import tarfile
        raw = _get(f"{EXPORTS}/sentences_with_audio.tar.bz2")
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:bz2") as t:
            audio_path.write_bytes(t.extractfile("sentences_with_audio.csv").read())

    text = {}
    with eng_path.open(encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) >= 3:
                text[r[0]] = r[2]

    ok = re.compile(r"^[A-Za-z ,.'?!]+$")
    # Learners are refugees/newcomers: skip distressing or politically loaded sentences.
    avoid = re.compile(
        r"murder|kill|dead|death|die[ds]?\b|diarrhea|rape|suicide|sex|drug|terror|war\b|bomb|"
        r"socialis|commun|nazi|hitler|iran|israel|palestin|islam|christ|jew|god\b|abandon|"
        r"suspend|poor|hate|traitor|vomit|blood|gun|shoot|prison|jail|torture|fuck|shit|klingon|toki|zamenhof|nonbinary|covid|vaccin|blasphem|scream|bankrupt|broke|esperanto|sami\b|tom\b|mali|drag|muslim|jesus|steal|swear|prudish|boyfriend|nightmare|gay|\bbi\b|coke|smoke|imam|\bpigs?\b|husband|ghost|snow|amoral|fat\b|brit|alcohol|beer|wine|sake|cock|queer|trans\b|homo|lesbian|jealous|upset|outrag|weapon|shut up|suck|trapped|cain|baghdad|iraq",
        re.I,
    )
    cands = []
    with audio_path.open(encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) < 4 or r[3] != LICENSE or r[0] not in text:
                continue
            t = text[r[0]]
            if ok.match(t) and not avoid.search(t) and 3 <= len(t.split()) <= 7:
                cands.append({"sentence_id": r[0], "audio_id": r[1], "user": r[2], "text": t})

    random.Random(seed).shuffle(cands)
    chosen, counts = [], {}
    for c in cands:
        if counts.get(c["user"], 0) < per_speaker:
            counts[c["user"]] = counts.get(c["user"], 0) + 1
            chosen.append(c)
        if len(chosen) == n:
            break
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="folder for the mp3s (git-ignored)")
    ap.add_argument("-n", type=int, default=25)
    ap.add_argument("--per-speaker", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between audio downloads")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    chosen = pick(args.out / "_exports", args.n, args.per_speaker, args.seed)
    rows = []
    for i, c in enumerate(chosen, 1):
        clip_id = f"tatoeba-{c['audio_id']}"
        dest = args.out / f"{clip_id}.mp3"
        if not dest.exists():
            dest.write_bytes(_get(AUDIO_URL.format(audio_id=c["audio_id"])))
            time.sleep(args.pause)
        rows.append({
            "clip_id": clip_id, "file": dest.name, "source": "Tatoeba",
            "source_url": f"https://tatoeba.org/en/sentences/show/{c['sentence_id']}",
            "license": LICENSE, "attribution": f"Audio by Tatoeba user {c['user']}",
            "target_text": c["text"], "accent_label": "unknown",
        })
        print(f"[{i}/{len(chosen)}] {clip_id}: {c['text']}")

    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {MANIFEST} ({len(rows)} clips)")


if __name__ == "__main__":
    main()
