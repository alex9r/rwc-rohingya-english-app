"""Command line: python -m ml.tts generate [--hero | --ids ID ...] / fetch-model"""

import argparse
import sys
from pathlib import Path

from .backends import DEFAULT_BACKEND, available_backends, fetch_kokoro_files, get_backend
from .generate import DEFAULT_LIMIT, HERO_IDS, generate, load_words, select_words

REPO = Path(__file__).resolve().parents[2]
# Stand-in until data/lexicon.json lands (Marcus). Same draft shape as the real one.
DEFAULT_LEXICON = REPO / "ml" / "translation" / "data" / "rohingya_greetings_30.json"


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m ml.tts", description="English TTS placeholder audio.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="create missing placeholder audio and update the manifest")
    which = g.add_mutually_exclusive_group()
    which.add_argument("--hero", action="store_true", help=f"only the hero words {', '.join(HERO_IDS)}")
    which.add_argument("--ids", nargs="+", metavar="ID", help="specific word ids")
    g.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="max words when no --hero/--ids")
    g.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON, help="lexicon JSON (read only)")
    g.add_argument("--out", type=Path, default=REPO / "data" / "audio")
    g.add_argument("--manifest", type=Path, default=REPO / "data" / "audio_manifest.json")
    g.add_argument("--backend", default=DEFAULT_BACKEND, help=f"one of: {', '.join(available_backends())}")
    g.add_argument("--voice", default=None, help="backend voice name")

    sub.add_parser("fetch-model", help="download the default engine's model files (public, no key)")
    args = ap.parse_args()

    if args.cmd == "fetch-model":
        for p in fetch_kokoro_files():
            print(p)
        return

    items = load_words(args.lexicon)
    if not items:
        sys.exit(f"no entries with an id and English text in {args.lexicon}")
    chosen, unknown = select_words(items, ids=list(HERO_IDS) if args.hero else args.ids, limit=args.limit)
    for u in unknown:
        print(f"unknown word id (skipped): {u}")
    opts = {"voice": args.voice} if args.voice else {}
    report = generate(chosen, args.out, args.manifest, get_backend(args.backend, **opts))
    for w in report.created:
        print(f"created  {w}")
    for w in report.skipped:
        print(f"skipped  {w} (already exists)")
    for w, why in report.failed:
        print(f"FAILED   {w}: {why}")
    for w in report.warnings:
        print(f"warning: {w}")
    print(report.summary())
    if report.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
