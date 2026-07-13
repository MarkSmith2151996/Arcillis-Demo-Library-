"""Compare extracted document JSON with arbitrary JSON ground truth."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = {"total_net_worth", "total_vat", "total_gross_worth"}
NUMERIC_FIELDS = {
    "item_qty",
    "item_net_price",
    "item_net_worth",
    "item_vat",
    "item_gross_worth",
    *SUMMARY_FIELDS,
}


def flatten_json(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dictionaries and lists into dotted, indexed scalar paths."""
    if isinstance(obj, dict):
        flattened: dict[str, Any] = {}
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(flatten_json(value, path))
        return flattened

    if isinstance(obj, list):
        flattened = {}
        for index, value in enumerate(obj):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            flattened.update(flatten_json(value, path))
        return flattened

    return {prefix: obj}


def normalize_text(value: Any) -> str:
    """Apply the requested case- and whitespace-insensitive string normalization."""
    return " ".join(str(value).split()).casefold()


def parse_date(value: Any) -> set[datetime.date]:
    """Parse common invoice dates, retaining both interpretations of ambiguous dates."""
    text = normalize_text(value)
    for separator in ("/", ".", "-"):
        text = text.replace(separator, "-")

    parsed_dates: set[datetime.date] = set()
    for date_format in ("%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%Y-%d-%m"):
        try:
            parsed_dates.add(datetime.strptime(text, date_format).date())
        except ValueError:
            continue
    return parsed_dates


def parse_number(value: Any) -> float | None:
    """Parse common currency, percentage, and decimal-comma invoice values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(" ", "")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text or text in {"-", ".", ","}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        whole, decimal = text.rsplit(",", 1)
        text = f"{whole.replace(',', '')}.{decimal}" if len(decimal) != 3 else text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def values_match(field_name: str, extracted: Any, expected: Any) -> bool:
    """Compare one scalar using the appropriate date, numeric, or text rule."""
    if field_name == "invoice_date":
        extracted_dates = parse_date(extracted)
        expected_dates = parse_date(expected)
        return bool(extracted_dates and expected_dates and extracted_dates.intersection(expected_dates))

    if field_name in NUMERIC_FIELDS:
        extracted_number = parse_number(extracted)
        expected_number = parse_number(expected)
        return (
            extracted_number is not None
            and expected_number is not None
            and abs(extracted_number - expected_number) <= 0.01
        )

    extracted_text = normalize_text(extracted)
    expected_text = normalize_text(expected)
    return extracted_text == expected_text or SequenceMatcher(None, extracted_text, expected_text).ratio() > 0.90


def grade_extraction(extracted_data: dict[str, Any], ground_truth: dict[str, Any]) -> tuple[dict[str, bool], float]:
    """Return field-level scores and the percentage of expected fields matched."""
    extracted = flatten_json(extracted_data)
    expected = flatten_json(ground_truth)
    scores: dict[str, bool] = {}

    for field_path, expected_value in expected.items():
        if expected_value is None or (
            isinstance(expected_value, str) and not expected_value.strip()
        ):
            continue

        if field_path not in extracted:
            scores[field_path] = False
            continue

        field_name = field_path.rsplit(".", 1)[-1]
        scores[field_path] = values_match(field_name, extracted[field_path], expected_value)

    accuracy = 100.0 * sum(scores.values()) / len(scores) if scores else 0.0
    return scores, accuracy


def main() -> int:
    """Grade two JSON files from the command line."""
    parser = argparse.ArgumentParser(description="Grade extracted invoice JSON against ground truth JSON.")
    parser.add_argument("extracted_json", type=Path)
    parser.add_argument("ground_truth_json", type=Path)
    args = parser.parse_args()
    extracted = json.loads(args.extracted_json.read_text(encoding="utf-8"))
    ground_truth = json.loads(args.ground_truth_json.read_text(encoding="utf-8"))
    scores, accuracy = grade_extraction(extracted, ground_truth)
    print(json.dumps({"field_scores": scores, "overall_accuracy": accuracy}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
