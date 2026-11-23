"""Load the JSON vocabulary datasets into DynamoDB (rwc-content).

    python -m app.dynamo_load [datasets...] [--dry-run] [--overwrite] [--create-table]

Uses the same IDs and fields as the Postgres seeder (app.seed), so both stores
serve identical entries.

Insert-only by default: an entry already in the table is skipped, because reviewers
correct content directly in DynamoDB (the data stack's ``reviewer`` policy) and a
re-load must never undo their work. ``--overwrite`` replaces existing entries with
the dataset version, corrections included, so use it deliberately. Category items
are always rewritten (their word counts are derived). Entries removed from a dataset
are NOT deleted from the table.

In AWS, run it with the content-loader role (the API's own role can't write content).
--create-table is for DynamoDB Local; in AWS, the data stack (infra/dynamodb.tf) owns
the table.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from app import seed, vocabulary_dynamo


def build_items(paths: Sequence[str | Path]) -> list[dict]:
    """Entry and category items laid out as in docs/aws-architecture.md"""
    items, category_names, counts = [], {}, Counter()
    for path in paths:
        dataset, entries = seed.load_dataset(path)
        for entry in entries:
            (word_id, dataset_name, source_id, category_id, category_name, english,
             rohingya, image_url, audio_url, status, entry_type, part_of_speech,
             confidence, confidence_tier, needs_review, entry_json) = seed._entry_values(
                dataset, entry
            )
            category_names[category_id] = category_name
            counts[category_id] += 1
            item = {
                "pk": f"ENTRY#{word_id}",
                "sk": "META",
                "id": word_id,
                "dataset": dataset_name,
                "source_id": source_id,
                "category_id": category_id,
                "category_name": category_name,
                "english_text": english,
                "rohingya_text": rohingya,
                "image_url": image_url,
                "audio_url": audio_url,
                "verification_status": status,
                "entry_type": entry_type,
                "part_of_speech": part_of_speech,
                # DynamoDB needs Decimal, and an unscored entry has no attribute at all.
                "confidence": Decimal(str(confidence)) if confidence is not None else None,
                "confidence_tier": confidence_tier,
                "needs_review": needs_review,
                "entry_json": entry_json,
                "gsi1pk": f"CATEGORY#{category_id}",
                "gsi1sk": english,
                "gsi2pk": f"STATUS#{status or 'unknown'}",
                "gsi2sk": f"{confidence if confidence is not None else 'none'}#{word_id}",
            }
            items.append({k: v for k, v in item.items() if v is not None})
    for category_id, name in category_names.items():
        items.append(
            {
                "pk": f"CATEGORY#{category_id}",
                "sk": "META",
                "id": category_id,
                "name": name,
                "word_count": counts[category_id],
            }
        )
    return items


# Index names and projections as defined in the data stack (infra/dynamodb.tf).
INDEXES = (("gsi1-category", "gsi1", "ALL"), ("gsi2-review", "gsi2", "KEYS_ONLY"))


def create_table(resource, name: str = vocabulary_dynamo.TABLE):
    """Same keys and indexes as infra/dynamodb.tf. For DynamoDB Local and tests only."""
    attributes = ["pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk"]
    return resource.create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in attributes],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": index,
                "KeySchema": [
                    {"AttributeName": f"{prefix}pk", "KeyType": "HASH"},
                    {"AttributeName": f"{prefix}sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": projection},
            }
            for index, prefix, projection in INDEXES
        ],
    )


@dataclass
class LoadResult:
    written: int  # entries written (new, or replaced with --overwrite)
    skipped: int  # entries already in the table and left alone
    categories: int  # category items written


def load(paths: Sequence[str | Path], table, overwrite: bool = False) -> LoadResult:
    from botocore.exceptions import ClientError

    result = LoadResult(written=0, skipped=0, categories=0)
    for item in build_items(paths):
        if not item["pk"].startswith("ENTRY#"):
            table.put_item(Item=item)  # category counts are derived: always refresh
            result.categories += 1
            continue
        if overwrite:
            table.put_item(Item=item)
            result.written += 1
            continue
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            result.written += 1
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            result.skipped += 1  # already there, possibly corrected by a reviewer
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("datasets", nargs="*", type=Path, help="JSON datasets to load")
    parser.add_argument("--dry-run", action="store_true", help="print items, write nothing")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace existing entries (undoes reviewer corrections)")
    parser.add_argument("--create-table", action="store_true",
                        help="create the table first (DynamoDB Local only)")
    args = parser.parse_args(argv)
    paths = args.datasets or seed.DEFAULT_DATASETS

    if args.dry_run:
        for item in build_items(paths):
            print(json.dumps(item, ensure_ascii=False, default=str))
        return 0

    if args.overwrite:
        print("WARNING: --overwrite replaces existing entries, including reviewer corrections.")
    dynamodb = vocabulary_dynamo.resource()
    if args.create_table:
        create_table(dynamodb).wait_until_exists()
    table = dynamodb.Table(vocabulary_dynamo.TABLE)
    result = load(paths, table, overwrite=args.overwrite)
    print(
        f"{table.name}: {result.written} entries written, {result.skipped} already present "
        f"(left as is), {result.categories} categories refreshed, from {len(paths)} dataset(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

