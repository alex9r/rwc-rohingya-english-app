#!/usr/bin/env python3
"""Word error rate for Whisper, using synthesized English with known text.

The blocker on every accuracy number so far has been that no recording exists
whose correct transcript is known. Text-to-speech removes that: we choose the
sentence, so the reference is exact.

This is not a substitute for recordings of real learners. TTS is clean, fluent
and has no disfluency, so absolute WER here will be optimistic. What it does
support is comparison: model against model, accent against accent, clean against
noisy. Those relative numbers are what a model recommendation rests on, and they
hold even though the speech is synthetic.

Three studies:

  models      WER per model size on clean audio. Which model to ship.
  accents     WER per TTS voice locale. An imperfect stand-in for accented
              speech, since no Rohingya-accented English recordings exist.
  conditions  WER under background noise and altered speaking rate, measured
              against the known text rather than against a clean transcript.

    python wer_benchmark.py generate
    python wer_benchmark.py models --models tiny base small medium
    python wer_benchmark.py accents --model small
    python wer_benchmark.py conditions --model small
    python wer_benchmark.py all

Needs macOS `say` and ffmpeg. Results append to wer_results.json and resume.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import string
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(os.getenv("RWC_REPO", Path.home() / "Desktop" / "rwc-rohingya-english-app"))
PHRASES_JSON = REPO / "ml" / "translation" / "data" / "rohingya_phrases_38.json"
OUT = Path(os.getenv("RWC_WER_OUT", Path.home() / "Desktop" / "voa_rhg" / "wer"))
AUDIO = OUT / "audio"
SR = 16000

# en_* voices shipped with macOS. The script keeps whichever are installed.
# Rishi is Indian English, the nearest available stand-in for South Asian
# accented English. None of these is Rohingya-accented English, which does not
# exist as a recording anywhere.
VOICES = [
    ("Samantha", "en_US"), ("Alex", "en_US"), ("Daniel", "en_GB"),
    ("Rishi", "en_IN"), ("Karen", "en_AU"), ("Moira", "en_IE"),
    ("Tessa", "en_ZA"), ("Fiona", "en_scotland"),
]

FALLBACK_PHRASES = [
    "Take your pills.", "Where is the bus stop?", "I need a doctor.",
    "How much does this cost?", "Can you help me please?",
    "I am looking for work.", "Where can I buy rice?",
    "What time does it open?", "I do not understand.",
    "Thank you very much.", "My name is Ahmed.", "I need to see a pharmacist.",
]


def log(m=""):
    print(m, flush=True)


# ------------------------------------------------------------------------ wer

def normalize(text: str) -> list[str]:
    """Lowercase, drop punctuation, collapse whitespace.

    Without this, "pills." and "pills" count as a substitution and every WER
    is inflated by the reference's own punctuation.
    """
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text).split()


def wer(reference: str, hypothesis: str) -> tuple[float, dict]:
    """Standard word error rate: (substitutions + deletions + insertions) / N."""
    r, h = normalize(reference), normalize(hypothesis)
    if not r:
        return (0.0 if not h else 1.0), {"S": 0, "D": 0, "I": len(h), "N": 0}

    # Levenshtein over words, with a backtrace to split the error types.
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=np.int32)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)

    i, j = len(r), len(h)
    S = D = I = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (r[i - 1] != h[j - 1]):
            S += r[i - 1] != h[j - 1]
            i, j = i - 1, j - 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            D += 1
            i -= 1
        else:
            I += 1
            j -= 1

    return (S + D + I) / len(r), {"S": S, "D": D, "I": I, "N": len(r)}


# ------------------------------------------------------------------- phrases

def load_phrases(limit: int) -> list[str]:
    """English sentences from the team's reviewed phrase set, if it is there."""
    if not PHRASES_JSON.exists():
        log(f"  {PHRASES_JSON.name} not found, using the built-in phrases")
        return FALLBACK_PHRASES[:limit]

    data = json.loads(PHRASES_JSON.read_text())
    out = []
    for e in data.get("entries", []):
        s = (e.get("example_sentence", {}).get("english")
             or e.get("english_meaning", {}).get("word"))
        if s and len(normalize(s)) >= 2:
            out.append(s.strip())
    seen, uniq = set(), []
    for s in out:
        if s.lower() not in seen:
            seen.add(s.lower())
            uniq.append(s)
    log(f"  {len(uniq)} phrases from {PHRASES_JSON.name}")
    return uniq[:limit]


# ----------------------------------------------------------------------- tts

def available_voices() -> list[tuple[str, str]]:
    try:
        r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                           check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    installed = {line.split()[0] for line in r.stdout.splitlines() if line.strip()}
    return [(v, loc) for v, loc in VOICES if v in installed]


def synthesize(text: str, voice: str, dest: Path) -> bool:
    if dest.exists():
        return True
    aiff = dest.with_suffix(".aiff")
    try:
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                       check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", str(SR),
                        "-ac", "1", str(dest)], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    finally:
        aiff.unlink(missing_ok=True)


def do_generate(n_phrases: int, results: dict) -> None:
    log("\n" + "=" * 64)
    log("GENERATE")
    log("=" * 64)

    voices = available_voices()
    if not voices:
        sys.exit("No macOS en_* voices found. Install some in System Settings "
                 "> Accessibility > Spoken Content > System Voice > Manage.")
    log(f"  voices: {', '.join(f'{v} ({l})' for v, l in voices)}")

    phrases = load_phrases(n_phrases)
    AUDIO.mkdir(parents=True, exist_ok=True)

    manifest = []
    for pi, text in enumerate(phrases):
        for voice, locale in voices:
            dest = AUDIO / f"p{pi:03d}_{voice}.wav"
            if synthesize(text, voice, dest):
                manifest.append({"file": dest.name, "text": text,
                                 "voice": voice, "locale": locale,
                                 "phrase_id": pi})
    results["manifest"] = manifest
    save(results)
    log(f"  {len(manifest)} clips from {len(phrases)} phrases "
        f"x {len(voices)} voices")


# ------------------------------------------------------------------- degrade

def add_noise(audio: np.ndarray, snr_db: float) -> np.ndarray:
    p = float(np.mean(audio ** 2))
    if p <= 0:
        return audio
    noise = np.random.default_rng(0).normal(
        0, np.sqrt(p / (10 ** (snr_db / 10))), audio.shape).astype(np.float32)
    out = audio + noise
    peak = float(np.max(np.abs(out)))
    return (out / peak * 0.98).astype(np.float32) if peak > 1.0 else out


def speed_shifted(path: Path, rate: float):
    """ffmpeg atempo, which keeps pitch where it is."""
    import whisper
    dest = OUT / "tmp_speed.wav"
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(path), "-filter:a",
                        f"atempo={rate}", "-ar", str(SR), "-ac", "1", str(dest)],
                       check=True, capture_output=True)
        return whisper.load_audio(str(dest))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    finally:
        dest.unlink(missing_ok=True)


# ------------------------------------------------------------------- studies

def transcribe_set(model, manifest, degrade=None):
    import whisper
    rows = []
    for m in manifest:
        path = AUDIO / m["file"]
        if not path.exists():
            continue
        audio = degrade(path) if degrade else whisper.load_audio(str(path))
        if audio is None:
            continue
        r = model.transcribe(audio, language="en", temperature=0.0, fp16=False)
        hyp = r["text"].strip()
        rate, counts = wer(m["text"], hyp)
        rows.append({**m, "hyp": hyp, "wer": round(rate, 4), **counts})
    return rows


def report(rows, label, key=None):
    if not rows:
        log(f"  {label}: nothing to report")
        return
    tot_err = sum(r["S"] + r["D"] + r["I"] for r in rows)
    tot_n = sum(r["N"] for r in rows)
    overall = tot_err / tot_n if tot_n else 0.0
    perfect = sum(1 for r in rows if r["wer"] == 0)
    log(f"  {label:14} WER {overall:6.1%}   perfect {perfect}/{len(rows)}")
    if key:
        groups = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r)
        for g, rs in sorted(groups.items()):
            e = sum(x["S"] + x["D"] + x["I"] for x in rs)
            n = sum(x["N"] for x in rs)
            log(f"      {g:14} {e / n:6.1%}  ({len(rs)} clips)")
    return overall


def do_models(model_names, results):
    import whisper
    log("\n" + "=" * 64)
    log("WER BY MODEL  (clean synthesized English)")
    log("=" * 64)

    manifest = results.get("manifest")
    if not manifest:
        sys.exit("Run `generate` first.")

    bucket = results.setdefault("models", {})
    for name in model_names:
        if name in bucket:
            log(f"{name}: done")
            continue
        log(f"{name}: loading")
        model = whisper.load_model(name)
        rows = transcribe_set(model, manifest)
        bucket[name] = rows
        report(rows, name)
        save(results)
        del model

    log("\n  Summary")
    for name in model_names:
        if name in bucket:
            report(bucket[name], name)


def do_accents(model_name, results):
    import whisper
    log("\n" + "=" * 64)
    log(f"WER BY VOICE LOCALE  ({model_name})")
    log("=" * 64)
    log("  A stand-in only. None of these is Rohingya-accented English.\n")

    manifest = results.get("manifest")
    if not manifest:
        sys.exit("Run `generate` first.")

    rows = results.get("models", {}).get(model_name)
    if not rows:
        model = whisper.load_model(model_name)
        rows = transcribe_set(model, manifest)
        results.setdefault("models", {})[model_name] = rows
        save(results)
    report(rows, model_name, key="locale")


def do_conditions(model_name, results):
    import whisper
    log("\n" + "=" * 64)
    log(f"WER UNDER NOISE AND SPEED  ({model_name})")
    log("=" * 64)
    log("  Against the known text, so this is real degradation, not drift.\n")

    manifest = results.get("manifest")
    if not manifest:
        sys.exit("Run `generate` first.")

    conditions = [
        ("clean", None),
        ("snr20", lambda p: add_noise(whisper.load_audio(str(p)), 20.0)),
        ("snr10", lambda p: add_noise(whisper.load_audio(str(p)), 10.0)),
        ("snr5", lambda p: add_noise(whisper.load_audio(str(p)), 5.0)),
        ("speed0.8", lambda p: speed_shifted(p, 0.8)),
        ("speed1.2", lambda p: speed_shifted(p, 1.2)),
        ("speed1.5", lambda p: speed_shifted(p, 1.5)),
    ]

    model = whisper.load_model(model_name)
    bucket = results.setdefault("conditions", {}).setdefault(model_name, {})
    for label, fn in conditions:
        if label in bucket:
            log(f"  {label}: done")
            continue
        rows = transcribe_set(model, manifest, degrade=fn)
        bucket[label] = rows
        report(rows, label)
        save(results)

    log("\n  Summary")
    for label, _ in conditions:
        if label in bucket:
            report(bucket[label], label)


# ---------------------------------------------------------------------- main

def save(results):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "wer_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("study",
                   choices=["generate", "models", "accents", "conditions", "all"])
    p.add_argument("--models", nargs="+",
                   default=["tiny", "base", "small", "medium"])
    p.add_argument("--model", default="small")
    p.add_argument("--phrases", type=int, default=12)
    a = p.parse_args()

    try:
        import whisper  # noqa: F401
    except ImportError:
        sys.exit("openai-whisper not installed for this interpreter.")

    OUT.mkdir(parents=True, exist_ok=True)
    rp = OUT / "wer_results.json"
    results = json.loads(rp.read_text()) if rp.exists() else {}

    if a.study in ("generate", "all") or "manifest" not in results:
        do_generate(a.phrases, results)
    if a.study in ("models", "all"):
        do_models(a.models, results)
    if a.study in ("accents", "all"):
        do_accents(a.model, results)
    if a.study in ("conditions", "all"):
        do_conditions(a.model, results)

    save(results)
    log(f"\nWritten to {rp}")


if __name__ == "__main__":
    import whisper  # noqa: F401,E402  (used inside the condition lambdas)
    main()
