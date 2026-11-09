#!/usr/bin/env python3
"""Transcribe the station ident, the one clip whose content we know.

The corpus has no transcripts, so there is nothing to compute WER against.
Clip 000001 of each shard is the broadcast opening and says "Voice of America,
Washington". That makes it the only clip where output can be checked against
known words without a Rohingya speaker.

For reference, Meta's MMS with the rhg adapter transcribed the same ident as
"gasof amerika wacingthon", a phonetic Rohingyalish spelling of the same
English words.

    python -m ml.evaluation.ident_check
    python -m ml.evaluation.ident_check --clip 000001 --model large-v3

Note that the ident is spoken in English, so a hit here verifies English
transcription in this corpus, not Rohingya.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import DEFAULT_CLIPS, detect_language, romanize, transcribe

TARGETS = ["america", "amerika", "amrika", "washington", "wacington",
           "wacingthon", "wasington", "voice", "gasof", "gazof"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="large-v3")
    p.add_argument("--clips", type=Path, default=DEFAULT_CLIPS)
    p.add_argument("--clip", default="000001", help="Clip id (default: 000001)")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()

    try:
        import whisper
    except ImportError:
        sys.exit("openai-whisper not installed.\n"
                 "  pip install -r ml/evaluation/requirements.txt")

    path = a.clips / f"{a.clip}.mp3"
    if not path.exists():
        sys.exit(f"{path} not found")

    print(f"Loading {a.model}", flush=True)
    model = whisper.load_model(a.model)

    print(f"\nClip {a.clip}, known to say 'Voice of America, Washington'\n")
    det = detect_language(model, path)
    print(f"  detect: {det['top1']} @ {det['top1_prob']:.3f}  "
          f"({', '.join(f'{k}:{v}' for k, v in det['top5'])})")

    result = {"clip": a.clip, "model": a.model, "detect": det}
    for label, kw in [("forced_en", {"language": "en"}),
                      ("forced_bn", {"language": "bn"}),
                      ("auto", {})]:
        t = transcribe(model, path, **kw)
        t["romanized"] = romanize(t["text"])
        t["hits"] = [w for w in TARGETS if w in t["romanized"]]
        result[label] = t
        print(f"\n  [{label}] lang={t['language']} loop={t['looping']} "
              f"lp={t['avg_logprob']}")
        print(f"    raw: {t['text'][:110]}")
        print(f"    rom: {t['romanized'][:110]}")
        print(f"    hits: {t['hits'] or 'none'}")

    found = sorted({h for k in ("forced_en", "forced_bn", "auto")
                    for h in result[k]["hits"]})
    print()
    if found:
        print(f"  Found {found}. The model is picking up real words on a clip")
        print("  whose content we know independently.")
    else:
        print("  No ident words found in any pass.")

    out = a.out or a.clips.parent / "ident_check.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n  Written to {out}")


if __name__ == "__main__":
    main()
