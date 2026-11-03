"""Command line: python -m ml.pronunciation clip.m4a "target text" """

import argparse
import json

from ml.speech.transcribe import DEFAULT_MODEL, transcribe

from .scorer import DEFAULT_FUZZY_THRESHOLD, MIN_CONFIDENCE, score_pronunciation


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m ml.pronunciation",
        description="Score a spoken English clip against a target word or sentence.",
    )
    ap.add_argument("audio", help="audio file")
    ap.add_argument("target", help="the word or sentence the learner was trying to say")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper model size")
    ap.add_argument("--threshold", type=float, default=DEFAULT_FUZZY_THRESHOLD,
                    help="fuzzy word-match threshold, 0-1")
    ap.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE,
                    help="below this ASR confidence the clip is not scored")
    args = ap.parse_args()

    def transcriber(audio, language):
        return transcribe(audio, language, model_size=args.model)

    r = score_pronunciation(
        args.audio, args.target, transcriber=transcriber,
        fuzzy_threshold=args.threshold, min_confidence=args.min_confidence,
    )
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
