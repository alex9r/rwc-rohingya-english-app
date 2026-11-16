#!/usr/bin/env python3
"""Evaluate a Whisper model on VOA Rohingya clips, with language controls.

Samples one clip from each of N broadcasts, then decodes each one three ways:
language detection, forced Bengali, forced English. Greedy at temperature 0,
because the default temperature fallback ends up near random sampling on audio
the model cannot handle and the output changes between runs.

The controls are not optional. Whisper small and medium collapse into a
repeated syllable whenever Bengali is forced, including on clean English and on
real Bengali speech. Without a control you cannot tell that apart from a
Rohingya-specific failure. This script runs an English and a Bengali TTS control
first and refuses to interpret the forced-Bengali results if the Bengali control
loops.

    python -m ml.evaluation.whisper_eval --model large-v3
    python -m ml.evaluation.whisper_eval --model small --clips /path/to/x0

Results are written after every clip, so the run is resumable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from .common import (DEFAULT_CLIPS, detect_language, is_looping, romanize,
                     sample_clips, transcribe)

# macOS `say` voices. Swap these if you are not on a Mac.
CONTROL_SPECS = [
    ("english", "en", "Daniel",
     "The quick brown fox jumps over the lazy dog. "
     "This is a control sentence for speech recognition testing."),
    ("bengali", "bn", "Piya",
     "আমি বাংলায় কথা বলছি। এটি একটি পরীক্ষার বাক্য।"),
]


def log(m: str) -> None:
    print(m, flush=True)


def build_controls(model, out_dir: Path) -> dict:
    """Synthesize and transcribe the control clips."""
    ctl_dir = out_dir / "controls"
    ctl_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    for name, lang, voice, text in CONTROL_SPECS:
        aiff, wav = ctl_dir / f"{name}.aiff", ctl_dir / f"{name}.wav"
        try:
            subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                           check=True, capture_output=True)
            subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000",
                            "-ac", "1", str(wav)],
                           check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log(f"  control {name}: could not synthesize ({e})")
            log(f"  Install the '{voice}' voice, or supply your own clip.")
            results[name] = {"error": str(e)}
            continue

        entry = {
            "expected_lang": lang,
            "spoken": text,
            "detect": detect_language(model, wav),
            "forced": transcribe(model, wav, language=lang),
        }
        results[name] = entry
        log(f"  {name}: detected {entry['detect']['top1']} "
            f"@ {entry['detect']['top1_prob']:.3f}")
        log(f"    forced {lang}: {entry['forced']['text'][:90]!r}")

    return results


def control_passed(controls: dict, name: str) -> bool:
    c = controls.get(name, {})
    return "forced" in c and not c["forced"]["looping"]


def run(model_name: str, clips_dir: Path, out_dir: Path, n_clips: int,
        seed: int) -> None:
    try:
        import whisper
    except ImportError:
        sys.exit("openai-whisper not installed.\n"
                 "  pip install -r ml/evaluation/requirements.txt")

    if not clips_dir.exists():
        sys.exit(f"No clips at {clips_dir}. See the README for the download.")

    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"
    results = (json.loads(results_path.read_text())
               if results_path.exists() else {"model": model_name})

    def save():
        results_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2))

    log(f"Loading {model_name}")
    model = whisper.load_model(model_name)

    log("\nControls (these decide whether the rest means anything)")
    controls = results.get("controls") or build_controls(model, out_dir)
    results["controls"] = controls
    save()

    bn_ok = control_passed(controls, "bengali")
    en_ok = control_passed(controls, "english")
    log(f"\n  English control: {'passed' if en_ok else 'FAILED'}")
    log(f"  Bengali control: {'passed' if bn_ok else 'FAILED'}")
    if not bn_ok:
        log("  Forced-Bengali output below cannot be read as evidence about")
        log("  Rohingya. The model fails on Bengali itself in this setup.")

    clips = sample_clips(clips_dir, n=n_clips, seed=seed)
    log(f"\n{len(clips)} clips from {len(clips)} broadcasts\n")

    per_clip = results.setdefault("clips", {})
    for i, (cid, url, dur) in enumerate(clips, 1):
        if cid in per_clip:
            log(f"[{i}/{len(clips)}] {cid} done already")
            continue
        path = clips_dir / f"{cid}.mp3"
        if not path.exists():
            log(f"[{i}/{len(clips)}] {cid} missing")
            continue

        date = re.search(r"/(\d{8})-", url)
        log(f"[{i}/{len(clips)}] {cid} {dur:.1f}s "
            f"broadcast {date.group(1) if date else '?'}")

        entry = {"duration": dur, "broadcast": url,
                 "detect": detect_language(model, path)}
        d = entry["detect"]
        log(f"    detect {d['top1']} @ {d['top1_prob']:.3f}  "
            f"({', '.join(f'{k}:{v}' for k, v in d['top5'])})")

        for label, kw in [("forced_bn", {"language": "bn"}),
                          ("forced_en", {"language": "en"}),
                          ("auto", {})]:
            t = transcribe(model, path, **kw)
            t["romanized"] = romanize(t["text"])
            entry[label] = t
            flag = ("LOOP" if t["looping"]
                    else "EMPTY" if not t["text"] else "ok")
            log(f"    {label:10} [{flag}] lp={t['avg_logprob']} "
                f"{t['text'][:70]!r}")

        per_clip[cid] = entry
        save()

    summarize(results, bn_ok, out_dir)


def summarize(results: dict, bn_ok: bool, out_dir: Path) -> None:
    clips = results.get("clips", {})
    n = len(clips)
    if not n:
        return

    log("\n" + "=" * 60)
    log(f"SUMMARY  {results['model']}  ({n} clips)")
    log("=" * 60)

    labels: dict[str, int] = {}
    for c in clips.values():
        labels[c["detect"]["top1"]] = labels.get(c["detect"]["top1"], 0) + 1
    probs = sorted(c["detect"]["top1_prob"] for c in clips.values())

    log(f"  detect top-1 = bn      {labels.get('bn', 0)}/{n}")
    log(f"  other labels           "
        f"{dict(sorted(((k, v) for k, v in labels.items() if k != 'bn'), key=lambda kv: -kv[1]))}")
    log(f"  detect confidence      min {probs[0]:.2f}  "
        f"median {probs[len(probs) // 2]:.2f}  max {probs[-1]:.2f}")

    for label in ("forced_bn", "forced_en", "auto"):
        if label not in next(iter(clips.values())):
            continue
        loops = sum(1 for c in clips.values() if c[label]["looping"])
        empty = sum(1 for c in clips.values() if not c[label]["text"])
        lps = sorted(c[label]["avg_logprob"] for c in clips.values()
                     if c[label]["avg_logprob"] is not None)
        line = f"  {label:10} loops {loops}/{n}, empty {empty}/{n}"
        if lps:
            line += (f", logprob {lps[0]:.2f} / {lps[len(lps) // 2]:.2f} "
                     f"/ {lps[-1]:.2f}")
        log(line)

    log(f"\n  Bengali control: {'passed' if bn_ok else 'FAILED'}")
    if not bn_ok:
        log("  >>> forced_bn numbers are not evidence about Rohingya.")

    lines = []
    for cid, c in sorted(clips.items()):
        lines.append(f"=== {cid}  {c['duration']:.1f}s  {c['broadcast']}")
        lines.append(f"detect: {c['detect']['top5']}")
        for label in ("forced_bn", "forced_en", "auto"):
            if label not in c:
                continue
            d = c[label]
            lines.append(f"[{label}] loop={d['looping']} "
                         f"cr={d['compression_ratio']} lp={d['avg_logprob']}")
            lines.append(f"  {d['text']}")
            if d.get("romanized") and d["romanized"] != d["text"].lower():
                lines.append(f"  rom: {d['romanized']}")
        lines.append("")
    (out_dir / "transcripts.txt").write_text("\n".join(lines),
                                             encoding="utf-8")
    log(f"\n  Written to {out_dir}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="large-v3",
                   help="Whisper model size (default: large-v3). Note that "
                        "small and medium fail the Bengali control.")
    p.add_argument("--clips", type=Path, default=DEFAULT_CLIPS,
                   help=f"Folder of .mp3 and .json clips (default: {DEFAULT_CLIPS})")
    p.add_argument("--out", type=Path, default=None,
                   help="Output folder (default: alongside the clips)")
    p.add_argument("--n", type=int, default=20, help="Clips to sample")
    p.add_argument("--seed", type=int, default=0,
                   help="Sampling seed. Keep it fixed to compare models.")
    a = p.parse_args()

    out = a.out or a.clips.parent / f"whisper_eval_{a.model.replace('.', '_')}"
    run(a.model, a.clips, out, a.n, a.seed)


if __name__ == "__main__":
    main()
