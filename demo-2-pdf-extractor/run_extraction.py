"""Run invoice extraction, grading, and result persistence for a dataset split."""

from __future__ import annotations

import argparse
import time
from collections import Counter
from typing import Any

import psycopg2
from psycopg2.extras import Json

from extract_invoice import ExtractionError, create_client, extract_invoice, verify_proxy
from grade_extraction import grade_extraction
from load_ground_truth import SPLITS, database_url


def fetch_invoices(connection: Any, split: str, limit: int | None) -> list[tuple[int, str, dict[str, Any], str]]:
    """Fetch one split's invoice records in a deterministic order."""
    query = """
        SELECT id, filename, ground_truth, image_path
        FROM arcillis.demo2_invoice
        WHERE split = %s
        ORDER BY id
    """
    params: list[Any] = [split]
    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


def insert_extraction(
    connection: Any,
    invoice_id: int,
    run_id: str,
    model_used: str,
    extracted_data: dict[str, Any],
    field_scores: dict[str, bool],
    accuracy: float,
    processing_time_ms: int,
) -> None:
    """Persist one successful extraction and its grading result."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO arcillis.demo2_extraction
                (invoice_id, run_id, model_used, extracted_data, field_scores, overall_accuracy, processing_time_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                invoice_id,
                run_id,
                model_used,
                Json(extracted_data),
                Json(field_scores),
                accuracy,
                processing_time_ms,
            ),
        )
    connection.commit()


def run_extraction(run_id: str, split: str = "test", limit: int | None = None) -> int:
    """Extract, grade, and store all selected invoices. Return successful count."""
    client = create_client()
    model_used = verify_proxy(client)
    with psycopg2.connect(database_url()) as connection:
        invoices = fetch_invoices(connection, split, limit)
        if not invoices:
            raise RuntimeError(
                f"No {split} invoices found in arcillis.demo2_invoice. Run load_ground_truth.py first."
            )

        accuracies: list[float] = []
        field_totals: Counter[str] = Counter()
        field_passes: Counter[str] = Counter()
        total_started = time.perf_counter()

        for position, (invoice_id, filename, ground_truth, image_path) in enumerate(invoices, start=1):
            started = time.perf_counter()
            try:
                extracted_data = extract_invoice(image_path, client=client, model=model_used)
                field_scores, accuracy = grade_extraction(extracted_data, ground_truth)
                processing_time_ms = round((time.perf_counter() - started) * 1000)
                insert_extraction(
                    connection,
                    invoice_id,
                    run_id,
                    model_used,
                    extracted_data,
                    field_scores,
                    accuracy,
                    processing_time_ms,
                )
            except (ExtractionError, OSError, ValueError) as error:
                print(f"Processing {position}/{len(invoices)} - {filename} - ERROR: {error}")
                continue

            accuracies.append(accuracy)
            for field_name, passed in field_scores.items():
                field_totals[field_name] += 1
                field_passes[field_name] += int(passed)
            print(f"Processing {position}/{len(invoices)} - {filename} - {accuracy:.0f}% accuracy")

    elapsed_seconds = time.perf_counter() - total_started
    if not accuracies:
        print(f"No invoices completed. Total time: {elapsed_seconds:.1f}s")
        return 0

    worst_fields = sorted(
        ((field_passes[field] / total, field) for field, total in field_totals.items()),
        key=lambda item: (item[0], item[1]),
    )[:5]
    print(f"Completed {len(accuracies)}/{len(invoices)} invoices in {elapsed_seconds:.1f}s")
    print(f"Average accuracy: {sum(accuracies) / len(accuracies):.2f}%")
    print(
        "Worst fields: "
        + ", ".join(f"{field} ({rate * 100:.0f}%)" for rate, field in worst_fields)
    )
    return len(accuracies)


def main() -> int:
    """Run the extraction batch CLI."""
    parser = argparse.ArgumentParser(description="Extract and grade a Donut invoice split.")
    parser.add_argument("--run-id", required=True, help="Identifier stored with every extraction result.")
    parser.add_argument("--split", choices=SPLITS, default="test")
    parser.add_argument("--limit", type=int, help="Maximum invoices to process (default: all).")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    try:
        run_extraction(args.run_id, args.split, args.limit)
    except ExtractionError as error:
        print(f"ERROR: {error}")
        return 2
    except (OSError, psycopg2.Error, RuntimeError) as error:
        print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
