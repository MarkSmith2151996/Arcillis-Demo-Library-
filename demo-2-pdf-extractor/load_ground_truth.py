"""Load the local Donut invoice ground truth into Postgres."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = PROJECT_DIR.parent
DATASET_DIR = PROJECT_DIR / "datasets" / "donut-invoices"
SPLITS = ("train", "test", "validation")
DEFAULT_DATABASE_URL = "postgresql://autocore_writer:autocore_pipeline_2026@localhost:5432/hive"


def database_url() -> str:
    """Return the configured Postgres URL after loading the local environment."""
    load_dotenv(REPOSITORY_DIR / ".env")
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def iter_ground_truth(split: str) -> Iterator[tuple[str, dict[str, Any], str]]:
    """Yield filename, parsed gt_parse, and absolute image path for one split."""
    metadata_path = DATASET_DIR / split / "metadata.jsonl"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata for {split}: {metadata_path}")

    with metadata_path.open(encoding="utf-8") as metadata_file:
        for line_number, line in enumerate(metadata_file, start=1):
            try:
                record = json.loads(line)
                ground_truth = record["gt_parse"]
                if isinstance(ground_truth, str):
                    ground_truth = json.loads(ground_truth)
                if not isinstance(ground_truth, dict):
                    raise ValueError("gt_parse must be a JSON object")
                filename = record["file_name"]
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid {metadata_path}:{line_number}: {error}") from error

            image_path = (DATASET_DIR / split / filename).resolve()
            yield filename, ground_truth, str(image_path)


def load_split(connection: Any, split: str) -> tuple[int, int]:
    """Insert one split idempotently and return (inserted, skipped) counts."""
    inserted = 0
    skipped = 0
    with connection.cursor() as cursor:
        for filename, ground_truth, image_path in iter_ground_truth(split):
            cursor.execute(
                "SELECT 1 FROM arcillis.demo2_invoice WHERE filename = %s",
                (filename,),
            )
            if cursor.fetchone():
                skipped += 1
                continue
            cursor.execute(
                """
                INSERT INTO arcillis.demo2_invoice
                    (filename, split, ground_truth, image_path)
                VALUES (%s, %s, %s, %s)
                """,
                (filename, split, Json(ground_truth), image_path),
            )
            inserted += 1
    connection.commit()
    return inserted, skipped


def load_all_ground_truth() -> dict[str, tuple[int, int]]:
    """Load every dataset split and return insertion counts by split."""
    results: dict[str, tuple[int, int]] = {}
    with psycopg2.connect(database_url()) as connection:
        for split in SPLITS:
            results[split] = load_split(connection, split)
    return results


def main() -> int:
    """Run the idempotent ground-truth loader from the command line."""
    parser = argparse.ArgumentParser(description="Load Donut invoice ground truth into Postgres.")
    parser.add_argument("--split", choices=SPLITS, help="Load just one dataset split.")
    args = parser.parse_args()

    splits = (args.split,) if args.split else SPLITS
    with psycopg2.connect(database_url()) as connection:
        for split in splits:
            inserted, skipped = load_split(connection, split)
            print(f"{split}: {inserted} invoices loaded, {skipped} duplicates skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
