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
    Path("ml/translation/data/rohingya_phrases_38.json"),
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


def _entry_type(entry: dict[str, Any]) -> str:
    # Phrase datasets are sentences; word datasets are headwords.
    return "phrase" if str(entry["id"]).startswith("phrase_") else "word"


def _needs_review(entry: dict[str, Any], reference: dict[str, Any]) -> bool:
    if "needs_review" in reference:
        return bool(reference["needs_review"]) or entry.get("validation_status") != "verified"
    return entry.get("validation_status") != "verified"


def _child_rows(word_id: str, entry: dict[str, Any]) -> dict[str, list[tuple]]:
    """Normalise the nested JSON into translation / media / source rows."""
    reference = entry.get("reference_translation") or {}
    example = entry.get("example_sentence") or {}
    alternative = entry.get("alternative_spellings_scripts") or {}
    translations: list[tuple] = []
    if entry.get("rohingya_text"):
        translations.append(
            (word_id, "headword", "rhg", "latn", entry["rohingya_text"],
             (entry.get("source_reference") or {}).get("evidence"),
             entry.get("validation_status"), None)
        )
    if example.get("english"):
        translations.append(
            (word_id, "example", "en", "latn", example["english"], None, None, None)
        )
    if example.get("rohingya"):
        translations.append(
            (word_id, "example", "rhg", "latn", example["rohingya"],
             example.get("example_origin"), example.get("translation_verification"), None)
        )
    if reference.get("rohingya"):
        translations.append(
            (word_id, "reference", "rhg", "latn", reference["rohingya"],
             reference.get("origin"), reference.get("confidence_tier"),
             reference.get("confidence"))
        )
    for text in alternative.get("latin") or []:
        translations.append((word_id, "variant", "rhg", "latn", text, None, None, None))

    media = []
    for kind, field in (("image", "image"), ("audio", "audio_pronunciation")):
        location = _asset_url(entry.get(field))
        if location:
            media.append((word_id, kind, location, None, False))

    sources = []
    ref = entry.get("source_reference")
    if ref:
        sources.append(
            (word_id, ref.get("title"), ref.get("url"), ref.get("lookup_term"),
             ref.get("evidence"), "primary")
        )
    for checked in entry.get("sources_checked") or []:
        sources.append(
            (word_id, checked.get("source"), None, None, checked.get("result"), "checked")
        )
    return {"translations": translations, "media": media, "sources": sources}


def _entry_values(dataset: str, entry: dict[str, Any]) -> tuple:
    category_name = str(entry.get("related_topic") or "Uncategorized")
    category_id = _slug(category_name)
    reference = entry.get("reference_translation") or {}
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
        _entry_type(entry),
        entry.get("part_of_speech"),
        reference.get("confidence"),
        reference.get("confidence_tier"),
        _needs_review(entry, reference),
        json.dumps(entry, ensure_ascii=False),
    )


def _replace_children(conn, word_id: str, entry: dict[str, Any]) -> None:
    """Rebuild a word's child rows so reseeding mirrors the dataset exactly."""
    for table in ("vocabulary_translations", "vocabulary_media", "vocabulary_sources"):
        conn.execute(f"DELETE FROM {table} WHERE word_id=%s", (word_id,))
    rows = _child_rows(word_id, entry)
    for row in rows["translations"]:
        conn.execute(
            "INSERT INTO vocabulary_translations "
            "(word_id, role, language, script, text, origin, verification, confidence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", row)
    for row in rows["media"]:
        conn.execute(
            "INSERT INTO vocabulary_media (word_id, kind, location, mime_type, verified) "
            "VALUES (%s, %s, %s, %s, %s)", row)
    for row in rows["sources"]:
        conn.execute(
            "INSERT INTO vocabulary_sources "
            "(word_id, title, url, lookup_term, evidence, kind) "
            "VALUES (%s, %s, %s, %s, %s, %s)", row)


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
                    "image_url, audio_url, verification_status, entry_type, part_of_speech, "
                    "confidence, confidence_tier, needs_review, entry_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                    "ON CONFLICT (dataset, source_id) DO UPDATE SET "
                    "id=EXCLUDED.id, category_id=EXCLUDED.category_id, "
                    "english_text=EXCLUDED.english_text, rohingya_text=EXCLUDED.rohingya_text, "
                    "image_url=EXCLUDED.image_url, audio_url=EXCLUDED.audio_url, "
                    "verification_status=EXCLUDED.verification_status, "
                    "entry_type=EXCLUDED.entry_type, part_of_speech=EXCLUDED.part_of_speech, "
                    "confidence=EXCLUDED.confidence, confidence_tier=EXCLUDED.confidence_tier, "
                    "needs_review=EXCLUDED.needs_review, entry_json=EXCLUDED.entry_json",
                    # values[4] is the category name, stored on vocabulary_categories.
                    values[:4] + values[5:],
                )
                _replace_children(conn, values[0], entry)
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
