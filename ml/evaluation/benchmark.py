#!/usr/bin/env python3
"""Whisper benchmarking: latency, decoding configs, and robustness.

Three studies, none of which need reference transcripts. They answer the parts
of the benchmarking task that are not blocked on the labelled dataset.

  latency     seconds of compute per second of audio, per model size.
              Decides what can actually ship.

  configs     beam size, VAD, and compute precision on one model. Speed cost
              and whether the output changes at all.

  robustness  background noise at several SNRs, and speaking rate at 0.8x and
              1.2x. Measured as drift from the clean transcript rather than
              accuracy, since there is no ground truth. A model whose output
              barely moves under noise is more trustworthy in a room with a
              kettle in it than one that rewrites itself.

Usage:
    python benchmark.py latency --models tiny base small medium
    python benchmark.py configs --model small
    python benchmark.py robustness --models small medium
    python benchmark.py all

Results append to benchmark_results.json and survive interruption. Start with
latency: if a model is too slow there, skip it in the other two.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

CLIPS = Path(os.getenv("RWC_VOA_CLIPS", Path.home() / "Desktop" / "voa_rhg" / "x0"))
OUT = Path(os.getenv("RWC_BENCH_OUT",
                     Path.home() / "Desktop" / "voa_rhg" / "benchmark"))
LANG = "en"  # forced language; large-v3 is the only size that survives this
SR = 16000


def log(m=""):
    print(m, flush=True)


# ----------------------------------------------------------------- results io

def load_results() -> dict:
    p = OUT / "benchmark_results.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_results(r: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "benchmark_results.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ clip pick

def pick_clips(n: int) -> list[tuple[str, float]]:
    """Longest-first from a fixed slice, so every study uses the same clips."""
    items = []
    for jp in sorted(CLIPS.glob("*.json"))[:400]:
        with open(jp) as fh:
            rec = json.load(fh)
        d = rec.get("duration", 0.0)
        if 8.0 <= d <= 15.0 and jp.stem != "000001":
            items.append((jp.stem, d))
    items.sort()
    step = max(1, len(items) // n)
    return items[::step][:n]


# -------------------------------------------------------------- audio helpers

def load_audio(clip_id: str) -> np.ndarray:
    import whisper
    return whisper.load_audio(str(CLIPS / f"{clip_id}.mp3"))


def add_noise(audio: np.ndarray, snr_db: float) -> np.ndarray:
    """Gaussian noise at a target signal-to-noise ratio."""
    sig_power = float(np.mean(audio ** 2))
    if sig_power <= 0:
        return audio
    noise_power = sig_power / (10 ** (snr_db / 10))
    noise = np.random.default_rng(0).normal(
        0, np.sqrt(noise_power), audio.shape).astype(np.float32)
    out = audio + noise
    peak = float(np.max(np.abs(out)))
    return (out / peak * 0.98).astype(np.float32) if peak > 1.0 else out


def change_speed(clip_id: str, rate: float) -> np.ndarray | None:
    """Time-stretch with ffmpeg atempo, which preserves pitch.

    Naive resampling would shift pitch too and confound the result, so this
    shells out rather than doing it in numpy.
    """
    src = CLIPS / f"{clip_id}.mp3"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        dst = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={rate}",
             "-ar", str(SR), "-ac", "1", dst],
            check=True, capture_output=True)
        import whisper
        return whisper.load_audio(dst)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log(f"    ffmpeg failed ({type(e).__name__}), skipping speed test")
        return None
    finally:
        Path(dst).unlink(missing_ok=True)


def similarity(a: str, b: str) -> float:
    """0 to 1. How much of the clean transcript survives the degradation."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


# -------------------------------------------------------------------- studies

def study_latency(models: list[str], n_clips: int, results: dict) -> None:
    import whisper

    log("\n" + "=" * 64)
    log("LATENCY")
    log("=" * 64)
    log("  Real-time factor is compute seconds per audio second.")
    log("  Below 1.0 is faster than real time. Above 5 is unusable live.\n")

    clips = pick_clips(n_clips)
    bucket = results.setdefault("latency", {})

    for name in models:
        if name in bucket:
            log(f"{name}: already measured")
            continue
        log(f"{name}: loading")
        t0 = time.perf_counter()
        try:
            model = whisper.load_model(name)
        except Exception as e:
            log(f"  could not load: {e}")
            continue
        load_s = time.perf_counter() - t0
        log(f"  loaded in {load_s:.1f}s")

        per_clip = []
        for cid, dur in clips:
            audio = load_audio(cid)
            t0 = time.perf_counter()
            r = model.transcribe(audio, language=LANG, temperature=0.0,
                                 fp16=False)
            elapsed = time.perf_counter() - t0
            per_clip.append({"clip": cid, "audio_s": dur,
                             "compute_s": round(elapsed, 2),
                             "rtf": round(elapsed / dur, 2),
                             "chars": len(r["text"].strip())})
            log(f"    {cid} {dur:.0f}s audio -> {elapsed:.1f}s "
                f"(rtf {elapsed / dur:.2f})")

        rtfs = sorted(c["rtf"] for c in per_clip)
        bucket[name] = {"load_s": round(load_s, 1), "clips": per_clip,
                        "rtf_median": rtfs[len(rtfs) // 2],
                        "rtf_max": rtfs[-1]}
        log(f"  median rtf {rtfs[len(rtfs) // 2]:.2f}, worst {rtfs[-1]:.2f}")
        save_results(results)
        del model

    log("\n  Summary")
    for name, d in bucket.items():
        verdict = ("fine" if d["rtf_median"] < 1 else
                   "slow" if d["rtf_median"] < 5 else "unusable live")
        log(f"    {name:10} rtf {d['rtf_median']:5.2f}  load {d['load_s']:5.1f}s"
            f"  {verdict}")


def study_configs(model_name: str, n_clips: int, results: dict) -> None:
    import whisper

    log("\n" + "=" * 64)
    log(f"CONFIGS  ({model_name})")
    log("=" * 64)
    log("  Does a bigger beam buy anything, and what does it cost.\n")

    clips = pick_clips(n_clips)
    bucket = results.setdefault("configs", {}).setdefault(model_name, {})
    model = whisper.load_model(model_name)

    variants = {
        "beam1_vad_off": {"beam_size": None, "condition_on_previous_text": False},
        "beam5_vad_off": {"beam_size": 5, "condition_on_previous_text": False},
        "beam1_ctx_on": {"beam_size": None, "condition_on_previous_text": True},
    }

    baseline_texts: dict[str, str] = {}
    for label, kw in variants.items():
        if label in bucket:
            log(f"{label}: done")
            baseline_texts.setdefault(
                label, bucket[label]["clips"][0]["text"] if bucket[label]["clips"] else "")
            continue
        log(f"{label}")
        per_clip, times = [], []
        for cid, dur in clips:
            audio = load_audio(cid)
            t0 = time.perf_counter()
            r = model.transcribe(audio, language=LANG, temperature=0.0,
                                 fp16=False, **kw)
            elapsed = time.perf_counter() - t0
            text = r["text"].strip()
            times.append(elapsed / dur)
            per_clip.append({"clip": cid, "rtf": round(elapsed / dur, 2),
                             "text": text})
            log(f"    {cid} rtf {elapsed / dur:.2f}  {text[:60]!r}")
        times.sort()
        bucket[label] = {"rtf_median": round(times[len(times) // 2], 2),
                         "clips": per_clip}
        save_results(results)

    log("\n  Agreement against beam1_vad_off")
    base = {c["clip"]: c["text"] for c in bucket["beam1_vad_off"]["clips"]}
    for label, d in bucket.items():
        sims = [similarity(base.get(c["clip"], ""), c["text"])
                for c in d["clips"]]
        mean_sim = sum(sims) / len(sims) if sims else 0.0
        log(f"    {label:16} rtf {d['rtf_median']:5.2f}  "
            f"agreement {mean_sim:.2f}")
    log("\n  If agreement is near 1.00, the extra compute changed nothing.")


def study_robustness(models: list[str], n_clips: int, results: dict) -> None:
    import whisper

    log("\n" + "=" * 64)
    log("ROBUSTNESS")
    log("=" * 64)
    log("  Drift from the clean transcript, not accuracy. 1.00 means the")
    log("  output did not move; 0.00 means it was rewritten entirely.\n")

    clips = pick_clips(n_clips)
    bucket = results.setdefault("robustness", {})

    conditions = [("clean", None), ("snr20", 20.0), ("snr10", 10.0),
                  ("snr5", 5.0), ("speed0.8", "0.8"), ("speed1.2", "1.2")]

    for name in models:
        mb = bucket.setdefault(name, {})
        if all(c[0] in mb for c in conditions):
            log(f"{name}: done")
            continue
        log(f"{name}: loading")
        model = whisper.load_model(name)

        for label, param in conditions:
            if label in mb:
                continue
            log(f"  {label}")
            per_clip = []
            for cid, dur in clips:
                if label == "clean":
                    audio = load_audio(cid)
                elif label.startswith("snr"):
                    audio = add_noise(load_audio(cid), float(param))
                else:
                    audio = change_speed(cid, float(param))
                    if audio is None:
                        break
                r = model.transcribe(audio, language=LANG, temperature=0.0,
                                     fp16=False)
                text = r["text"].strip()
                segs = r.get("segments") or []
                per_clip.append({
                    "clip": cid, "text": text,
                    "avg_logprob": round(
                        sum(s["avg_logprob"] for s in segs) / len(segs), 3
                    ) if segs else None,
                })
                log(f"    {cid} {text[:60]!r}")
            if per_clip:
                mb[label] = {"clips": per_clip}
                save_results(results)
        del model

        clean = {c["clip"]: c["text"] for c in mb.get("clean", {}).get("clips", [])}
        log(f"\n  {name} drift from clean")
        for label, _ in conditions:
            if label == "clean" or label not in mb:
                continue
            sims = [similarity(clean.get(c["clip"], ""), c["text"])
                    for c in mb[label]["clips"]]
            lps = [c["avg_logprob"] for c in mb[label]["clips"]
                   if c["avg_logprob"] is not None]
            line = (f"    {label:10} agreement "
                    f"{sum(sims) / len(sims):.2f}" if sims else f"    {label:10}")
            if lps:
                line += f"   mean logprob {sum(lps) / len(lps):.2f}"
            log(line)


# ----------------------------------------------------------------------- main

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("study", choices=["latency", "configs", "robustness", "all"])
    p.add_argument("--models", nargs="+",
                   default=["tiny", "base", "small", "medium"])
    p.add_argument("--model", default="small", help="for the config sweep")
    p.add_argument("--clips", type=int, default=5)
    a = p.parse_args()

    try:
        import whisper  # noqa: F401
    except ImportError:
        sys.exit("openai-whisper not installed for this interpreter.")

    if not CLIPS.exists():
        sys.exit(f"No clips at {CLIPS}. Set RWC_VOA_CLIPS.")

    OUT.mkdir(parents=True, exist_ok=True)
    results = load_results()

    if a.study in ("latency", "all"):
        study_latency(a.models, a.clips, results)
    if a.study in ("configs", "all"):
        study_configs(a.model, a.clips, results)
    if a.study in ("robustness", "all"):
        study_robustness([a.model], a.clips, results)

    save_results(results)
    log(f"\nWritten to {OUT / 'benchmark_results.json'}")


if __name__ == "__main__":
    main()
