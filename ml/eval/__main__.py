"""python -m ml.eval {validate,run,prompts} ..."""

from __future__ import annotations

import argparse
import json
import sys

from . import manifest, prompts, runner


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ml.eval")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a manifest without running any model")
    v.add_argument("manifest")
    v.add_argument("--allow-unverified", action="store_true")

    r = sub.add_parser("run", help="transcribe every clip and write the error report")
    r.add_argument("manifest")
    r.add_argument("--language", default=None, help="Whisper proxy code: bn, ur, en (default: auto-detect)")
    r.add_argument("--model", default="small")
    r.add_argument("--fold-marks", action="store_true", help="ignore ' * - spelling marks")
    r.add_argument("--allow-unverified", action="store_true")
    r.add_argument("--out", default="eval_report", help="writes <out>.json and <out>.md")

    g = sub.add_parser("prompts", help="draw a recording-prompt manifest template from the Gamayun kit")
    g.add_argument("kit_dir")
    g.add_argument("out")
    g.add_argument("-n", type=int, default=100)
    g.add_argument("--max-words", type=int, default=8)

    a = p.parse_args(argv)
    try:
        if a.cmd == "prompts":
            print(f"wrote {prompts.build(a.kit_dir, a.out, n=a.n, max_words=a.max_words)} prompts to {a.out}")
            return 0
        clips = manifest.load(a.manifest, allow_unverified=a.allow_unverified)
        if a.cmd == "validate":
            print(f"ok: {len(clips)} clips, {len({c.speaker_id for c in clips})} speakers")
            return 0
        report = runner.evaluate(clips, runner.whisper_transcriber(a.model),
                                 asr_language=a.language, fold_marks=a.fold_marks)
    except manifest.ManifestError as e:
        print(e, file=sys.stderr)
        return 2
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    md = runner.to_markdown(report)
    with open(a.out + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
