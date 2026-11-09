"""Shared helpers for the Whisper evaluation scripts."""

from __future__ import annotations

import json
import os
import random
import unicodedata
import zlib
from collections import defaultdict
from pathlib import Path

# Whisper's own degeneracy threshold. Above this the text is repeating.
HALLUCINATION_COMPRESSION_RATIO = 2.4

DEFAULT_CLIPS = Path(
    os.getenv("RWC_VOA_CLIPS", Path.home() / "voa_rhg" / "x0")
)


def compression_ratio(text: str) -> float:
    if not text.strip():
        return 0.0
    data = text.encode("utf-8")
    return len(data) / len(zlib.compress(data))


def top_repeat_fraction(text: str) -> float:
    """Share of tokens taken by the single most common token."""
    toks = text.split()
    if len(toks) < 4:
        return 0.0
    counts: dict[str, int] = defaultdict(int)
    for t in toks:
        counts[t] += 1
    return max(counts.values()) / len(toks)


def is_looping(text: str) -> bool:
    return (compression_ratio(text) > HALLUCINATION_COMPRESSION_RATIO
            or top_repeat_fraction(text) > 0.4)


def sample_clips(clips_dir: Path, n: int = 20, seed: int = 0,
                 skip_first: int = 15, skip_last: int = 10,
                 min_duration: float = 5.0) -> list[tuple[str, str, float]]:
    """One clip from each of n different broadcasts.

    Broadcast openings and closings are skipped because every broadcast starts
    with the same station ident, which would otherwise dominate the sample.
    Returns (clip_id, broadcast_url, duration).
    """
    by_broadcast: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for jp in sorted(clips_dir.glob("*.json")):
        with open(jp) as fh:
            rec = json.load(fh)
        by_broadcast[rec.get("download_url", "")].append(
            (jp.stem, rec.get("duration", 0.0))
        )

    rng = random.Random(seed)
    chosen = []
    for url in sorted(by_broadcast):
        items = sorted(by_broadcast[url])
        pool = items[skip_first:len(items) - skip_last]
        pool = [(i, d) for i, d in pool if d >= min_duration and i != "000001"]
        if pool:
            cid, dur = rng.choice(pool)
            chosen.append((cid, url, dur))

    rng.shuffle(chosen)
    return chosen[:n]


def detect_language(model, path) -> dict:
    """Whisper's language ID with the top 5 candidates."""
    import whisper
    audio = whisper.pad_or_trim(whisper.load_audio(str(path)))
    mel = whisper.log_mel_spectrogram(
        audio, n_mels=model.dims.n_mels
    ).to(model.device)
    _, probs = model.detect_language(mel)
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])[:5]
    return {
        "top1": ranked[0][0],
        "top1_prob": float(ranked[0][1]),
        "top5": [(k, round(float(v), 4)) for k, v in ranked],
    }


def transcribe(model, path, **kwargs) -> dict:
    """One greedy decode with the loop metrics attached."""
    r = model.transcribe(str(path), temperature=0.0, fp16=False, **kwargs)
    text = r["text"].strip()
    segments = r.get("segments") or []
    return {
        "text": text,
        "language": r.get("language"),
        "compression_ratio": round(compression_ratio(text), 2),
        "top_repeat": round(top_repeat_fraction(text), 2),
        "looping": is_looping(text),
        "avg_logprob": round(
            sum(s["avg_logprob"] for s in segments) / len(segments), 3
        ) if segments else None,
    }


# Rough Bengali/Devanagari to Latin mapping. Not a correct transliteration, it
# exists so you can eyeball whether a word like "amerika" is hiding inside
# Bengali script without reading Bengali. Do not quote its output as a
# transliteration.
_ROMAN = {
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u", "এ": "e",
    "ঐ": "oi", "ও": "o", "ঔ": "ou", "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh",
    "ঙ": "ng", "চ": "c", "ছ": "ch", "জ": "j", "ঝ": "jh", "ঞ": "n", "ট": "t",
    "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n", "ত": "t", "থ": "th", "দ": "d",
    "ধ": "dh", "ন": "n", "প": "p", "ফ": "f", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "z", "র": "r", "ল": "l", "শ": "c", "ষ": "c", "স": "s", "হ": "h",
    "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t", "া": "a", "ি": "i", "ী": "i",
    "ু": "u", "ূ": "u", "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou", "্": "",
    "ং": "ng", "ঃ": "h", "ঁ": "n",
    "अ": "o", "आ": "a", "इ": "i", "उ": "u", "ए": "e", "ओ": "o", "क": "k",
    "ख": "kh", "ग": "g", "घ": "gh", "च": "c", "छ": "ch", "ज": "j", "झ": "jh",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th",
    "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "f", "ब": "b", "भ": "bh",
    "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "c", "ष": "c",
    "स": "s", "ह": "h", "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u",
    "े": "e", "ै": "oi", "ो": "o", "ौ": "ou", "्": "", "ं": "ng", "ः": "h",
}


def romanize(text: str) -> str:
    out = []
    for ch in text:
        if ch in _ROMAN:
            out.append(_ROMAN[ch])
        elif ch.isascii():
            out.append(ch)
        else:
            d = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in d if c.isascii()))
    return "".join(out).lower()
