"""Command line: python -m ml.speech clip.m4a [more clips] --language bn"""

import argparse
import json

from .transcribe import DEFAULT_MODEL, transcribe


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m ml.speech", description="Transcribe audio clips with Whisper.")
    ap.add_argument("files", nargs="+", help="audio files")
    ap.add_argument("--language", default=None, help="proxy language code, e.g. bn, ur, en")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper model size")
    args = ap.parse_args()

    for f in args.files:
        r = transcribe(f, args.language, model_size=args.model)
        print(json.dumps({"file": f, **r.to_dict()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
