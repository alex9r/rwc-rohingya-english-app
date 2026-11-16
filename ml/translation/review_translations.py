
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

    for item in load(PENDING, []):
        if (
            norm(item["input"]) == norm(text)
            and item["direction"] == direction
            and item["status"] == "pending_review"
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
    items = load(PENDING, [])

    # Avoid storing the same suggestion multiple times.
    for item in items:
        if (
            item["input"] == text
            and item["translation"] == translation
            and item["direction"] == direction
        ):
            return item["id"]

    item = {
        "id": uuid.uuid4().hex[:12],
        "input": text,
        "translation": translation,
        "direction": direction,
        "provider": provider,
        "source": provider,
        "status": "pending_review",
        "verification_status": "pending_review",
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
        translation = corrected or item["translation"]
        source = item.get("source") or item.get("provider") or "llm"

        if item["direction"] == "en->roh":
            en, roh = item["input"], translation
        else:
            en, roh = translation, item["input"]

        data = load(APPROVED, {
            "dataset": "Approved Translations",
            "entries": []
        })

        if any(
            e["english_meaning"]["word"] == en
            and e["rohingya_text"] == roh
            for e in data["entries"]
        ):
            print("Translation already approved.")
        else:
            # Keep source attribution + verification after approval.
            data["entries"].append({
                "id": item["id"],
                "english_meaning": {"word": en},
                "rohingya_text": roh,
                "source": source,
                "verification_status": "approved",
                "validation_status": "community_verified",
                "reviewed_by": reviewer,
                "source_reference": {
                    "title": "Human-reviewed LLM suggestion",
                    "provider": source,
                },
            })

            data["entry_count"] = len(data["entries"])
            save(APPROVED, data)
            print("Approved and added to dictionary.")

    else:
        print("Translation rejected.")

    items.remove(item)
    save(PENDING, items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "approve", "reject"])
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

        if args.action == "approve" and not args.reviewer:
            parser.error("Approval requires --reviewer")

        review(
            args.id,
            approve=args.action == "approve",
            reviewer=args.reviewer,
            corrected=args.translation
        )
