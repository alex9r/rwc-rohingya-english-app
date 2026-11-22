
"""Store and review LLM-generated translations."""

import argparse
import json
import os
import uuid
from pathlib import Path

HERE = Path(__file__).parent
PENDING = HERE / "data" / "pending_translations.json"
APPROVED = HERE / "data" / "approved_translations.json"


def load(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_pending(text, direction):
    from .translate import norm

    items = load(PENDING, [])

    for item in items:
        if (
            norm(item["input"]) == norm(text)
            and item["direction"] == direction
            and item.get("verification_status") == "pending_review"
        ):
            return item

    return None


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def save_pending(text, translation, direction, provider):
    from .translate import norm

    items = load(PENDING, [])

    # Prevent duplicate requests for the same phrase.
    for item in items:
        if (
            norm(item["input"]) == norm(text)
            and item["direction"] == direction
            and item.get("verification_status") == "pending_review"
        ):
            return item["id"]

    item = {
        "id": uuid.uuid4().hex[:12],
        "input": text,
        "translation": translation,
        "direction": direction,
        "source": provider,
        "verification_status": "pending_review"
    }

    items.append(item)
    save(PENDING, items)
    return item["id"]


def review(item_id, approve=False, reviewer=None, corrected=None):
    items = load(PENDING, [])
    item = next((x for x in items if x["id"] == item_id), None)

    if item is None:
        print("Translation not found.")
        return

    if approve:
        translation = corrected if corrected is not None else item["translation"]
        source = item["source"]

        if item["direction"] == "en->roh":
            en, roh = item["input"], translation
        else:
            en, roh = translation, item["input"]

        data = load(APPROVED, {
            "dataset": "Approved Translations",
            "schema_version": "draft-1",
            "entries": [],
            "entry_count": 0
        })

        if any(
            e["english_meaning"]["word"] == en
            and e["rohingya_text"] == roh
            for e in data["entries"]
        ):
            print("Translation already approved.")
        else:
            data["entries"].append({
                "id": item["id"],
                "rohingya_text": roh,
                "english_meaning": {
                    "word": en,
                    "definition": None,
                    "explanation": None
                },
                "part_of_speech": None,
                "source": source,
                "source_reference": {
                    "title": "Google Gemini" if source == "gemini" else source,
                    "url": None,
                    "lookup_term": item["input"],
                    "evidence": "human_reviewed_ai_translation"
                },
                "related_topic": None,
                "example_sentence": {
                    "english": en,
                    "rohingya": roh,
                    "translation_verification": "community_verified",
                    "example_origin": "ai_generated",
                    "example_source_url": None
                },
                "alternative_spellings_scripts": {
                    "latin": [],
                    "other_scripts": None
                },
                "audio_pronunciation": None,
                "image": None,
                "different_forms": [],
                "verification_status": "approved",
                "validation_status": "community_verified",
                "reviewed_by": reviewer
            })

            data["entry_count"] = len(data["entries"])
            save(APPROVED, data)
            print("Approved and added to dictionary.")

    else:
        print("Translation rejected.")

    items.remove(item)
    save(PENDING, items)


def unapprove(item_id):
    data = load(APPROVED, {"entries": []})
    entry = next((e for e in data["entries"] if e["id"] == item_id), None)

    if entry is None:
        print("Approved translation not found.")
        return

    pending = load(PENDING, [])

    pending_item = {
        "id": entry["id"],
        "input": entry["english_meaning"]["word"],
        "translation": entry["rohingya_text"],
        "direction": "en->roh",
        "source": entry.get("source", "gemini"),
        "verification_status": "pending_review"
    }

    if any(x["id"] == item_id for x in pending):
        print("Translation already pending.")
        return

    pending.append(pending_item)
    save(PENDING, pending)

    data["entries"].remove(entry)
    data["entry_count"] = len(data["entries"])
    save(APPROVED, data)

    print("Moved translation back to pending review.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["list", "approve", "reject", "unapprove"]
    )
    parser.add_argument("id", nargs="?")
    parser.add_argument("--reviewer")
    parser.add_argument("--translation")
    args = parser.parse_args()

    if args.action == "list":
        for item in load(PENDING, []):
            source = item.get("source") or item.get("provider") or "llm"
            status = item.get("verification_status") or item.get("status")
            print(
                f'{item["id"]}: {item["input"]} -> '
                f'{item["translation"]} ({item["direction"]}, '
                f'source={source}, verification={status})'
            )
    else:
        if not args.id:
            parser.error("Provide a translation ID")

        if args.action == "unapprove":
            unapprove(args.id)
        else:
            review(
                args.id,
                approve=args.action == "approve",
                reviewer=args.reviewer,
                corrected=args.translation
            )
