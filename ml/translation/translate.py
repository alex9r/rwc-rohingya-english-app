
"""Dictionary-first Rohingya-English translation with LLM fallback."""

import glob
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher

from .model_fallback import generate, ModelUnavailable
from .review_translations import get_pending, save_pending

THRESHOLD = 0.85
DATA = os.path.join(os.path.dirname(__file__), "data")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("(not verified)", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _entry_source(entry, filename):
    """Source attribution for a stored dictionary/approved entry."""
    ref = entry.get("source_reference") or {}
    if entry.get("source"):
        return entry["source"]
    if filename == "approved_translations.json" and ref.get("provider"):
        return ref["provider"]
    return "dictionary"


def _entry_verification(entry):
    """Verification status: approved or pending_review."""
    # Lexicon / approved files are lookup-trusted; pending stays out of _load().
    return entry.get("verification_status") or "approved"


def _load():
    # Each pair: (english, rohingya, source, verification_status)
    pairs = []

    for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        # Pending translations are not approved dictionary entries.
        filename = os.path.basename(path)
        if filename == "pending_translations.json":
            continue

        with open(path, encoding="utf-8") as f:
            entries = json.load(f)["entries"]

        for e in entries:
            ex = e.get("example_sentence") or {}
            source = _entry_source(e, filename)
            verification = _entry_verification(e)

            for en, roh in (
                (e["english_meaning"]["word"], e.get("rohingya_text")),
                (ex.get("english"), ex.get("rohingya"))
            ):
                if en and roh:
                    pairs.append((
                        en,
                        roh.replace("(not verified)", "").strip(),
                        source,
                        verification,
                    ))

    return pairs


PAIRS = _load()


def _call_model(text, direction):
    provider = os.getenv("TRANSLATION_PROVIDER", "").strip().lower()

    if provider not in ("gemini", "openai", "anthropic"):
        return None

    try:
        translation = generate(text, direction, provider)
        return translation, provider
    except ModelUnavailable:
        return None


def translate(text, direction):
    def out(
        t,
        s,
        c=0.0,
        source="dictionary",
        verification_status="approved",
        needs_review=False,
        alternatives=None,
    ):
        result = {
            "translation": t,
            "status": s,
            "confidence": None if c is None else round(c, 2),
            "source": source,
            "verification_status": verification_status,
            "needs_review": needs_review,
        }
        if alternatives is not None:
            result["alternatives"] = alternatives
        return result

    try:
        if direction not in ("en->roh", "roh->en"):
            return out(None, "failed")

        if not isinstance(text, str) or not norm(text):
            return out(None, "failed")

        src, dst = (0, 1) if direction == "en->roh" else (1, 0)
        q = norm(text)

        best, best_score = None, 0.0
        # Top-score dictionary hits (for ambiguity checks).
        top_matches = []

        # 1. Search dictionary first.
        for pair in PAIRS:
            score = SequenceMatcher(
                None, q, norm(pair[src])
            ).ratio()

            if score > best_score:
                best, best_score = pair, score
                top_matches = [pair]
            elif score == best_score and score > 0:
                top_matches.append(pair)

        if best and best_score >= THRESHOLD:
            # Distinct translations among tied best matches.
            alternatives = []
            seen = set()
            for pair in top_matches:
                key = norm(pair[dst])
                if key and key not in seen:
                    seen.add(key)
                    alternatives.append(pair[dst])

            if len(alternatives) > 1:
                # Ambiguous: do not pick one, and do not call the LLM.
                return out(
                    None,
                    "uncertain",
                    best_score,
                    source=best[2],
                    verification_status=best[3],
                    needs_review=best[3] == "pending_review",
                    alternatives=alternatives,
                )

            return out(
                alternatives[0],
                "ok",
                best_score,
                source=best[2],
                verification_status=best[3],
                needs_review=best[3] == "pending_review",
            )

        # 2. Reuse an existing pending translation.
        pending = get_pending(text, direction)

        if pending:
            provider = pending.get("source") or pending.get("provider") or "llm"
            return out(
                pending["translation"],
                "uncertain",
                None,
                source=provider,
                verification_status="pending_review",
                needs_review=True,
            )

        # 3. Call LLM only for new unsupported phrases.
        model_result = _call_model(text, direction)

        if model_result is not None:
            translation, provider = model_result

            # 4. Save generated translation for human review.
            try:
                save_pending(text, translation, direction, provider)
            except (OSError, ValueError, json.JSONDecodeError) as e:
                print(f"Could not save pending translation: {e}")

            return out(
                translation,
                "uncertain",
                None,
                source=provider,
                verification_status="pending_review",
                needs_review=True,
            )

        return out(None, "uncertain", best_score)

    except Exception as e:
        print(f"Translation error: {type(e).__name__}: {e}")
        return out(None, "failed")
