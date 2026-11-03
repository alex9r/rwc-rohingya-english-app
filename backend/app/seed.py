"""Load curated JSON vocabulary datasets into the backend PostgreSQL database."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

from app import db

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
# greetings_30 is a strict subset of greetings_40, so it is not seeded by default.
_DEFAULT_DATASET_PATHS = (
    Path("ml/translation/data/rohingya_greetings_40.json"),
    Path("ml/translation/data/rohingya_phrases_18.json"),
)


def _find_dataset(relative: Path) -> Path:
    for root in (REPOSITORY_ROOT, BACKEND_ROOT):
        if (root / relative).exists():
            return root / relative
    raise FileNotFoundError(relative)


DEFAULT_DATASETS = [_find_dataset(path) for path in _DEFAULT_DATASET_PATHS]


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-") or "dataset"


def load_dataset(path: str | Path) -> tuple[str, list[dict[str, Any]]]:
    """Read and validate a JSON dataset containing an ``entries`` array."""
    source = Path(path)
    with source.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError(f"{source} must be a JSON object containing an 'entries' array")

    dataset = str(data.get("dataset") or source.stem).strip() or source.stem
    entries = data["entries"]
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("id"):
            raise ValueError(f"{source}: entries[{index}] must be an object with an id")
        meaning = entry.get("english_meaning")
        if not isinstance(meaning, dict) or not meaning.get("word"):
            raise ValueError(f"{source}: entries[{index}] is missing english_meaning.word")
    return dataset, entries


def _asset_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        url = value.get("url") or value.get("path")
        return url if isinstance(url, str) else None
    return None


def _entry_values(dataset: str, entry: dict[str, Any]) -> tuple:
    category_name = str(entry.get("related_topic") or "Uncategorized")
    category_id = _slug(category_name)
    dataset_key = f"{_slug(dataset)}-{hashlib.sha256(dataset.encode()).hexdigest()[:10]}"
    return (
        f"{dataset_key}:{entry['id']}",
        dataset,
        str(entry["id"]),
        category_id,
        category_name,
        str(entry["english_meaning"]["word"]),
        entry.get("rohingya_text"),
        _asset_url(entry.get("image")),
        _asset_url(entry.get("audio_pronunciation")),
        entry.get("validation_status"),
        json.dumps(entry, ensure_ascii=False),
    )


def seed_datasets(paths: Sequence[str | Path]) -> int:
    """Idempotently insert or update entries from one or more JSON files."""
    datasets = [load_dataset(path) for path in paths]
    with db._connect() as conn:
        db.ensure_vocabulary_schema(conn)
        for dataset, entries in datasets:
            for entry in entries:
                values = _entry_values(dataset, entry)
                conn.execute(
                    "INSERT INTO vocabulary_categories (id, name) VALUES (%s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
                    (values[3], values[4]),
                )
                conn.execute(
                    "INSERT INTO vocabulary_words "
                    "(id, dataset, source_id, category_id, english_text, rohingya_text, "
                    "image_url, audio_url, verification_status, entry_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                    "ON CONFLICT (dataset, source_id) DO UPDATE SET "
                    "id=EXCLUDED.id, category_id=EXCLUDED.category_id, "
                    "english_text=EXCLUDED.english_text, rohingya_text=EXCLUDED.rohingya_text, "
                    "image_url=EXCLUDED.image_url, audio_url=EXCLUDED.audio_url, "
                    "verification_status=EXCLUDED.verification_status, "
                    "entry_json=EXCLUDED.entry_json",
                    values,
                )
    return sum(len(entries) for _, entries in datasets)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", nargs="*", type=Path, help="JSON datasets to import")
    args = parser.parse_args(argv)
    paths = args.datasets or DEFAULT_DATASETS
    count = seed_datasets(paths)
    print(f"Seeded {count} entries from {len(paths)} dataset(s) into PostgreSQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
