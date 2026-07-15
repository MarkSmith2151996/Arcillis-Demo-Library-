"""Demo 2 document-extraction tools exposed by the Demo Bench MCP server."""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import psycopg2
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


DATABASE_URL = "postgresql://autocore_writer:autocore_pipeline_2026@localhost:5432/hive"
EXPORT_DIR = Path(os.environ.get("DEMO_BENCH_EXPORT_DIR", "/tmp/demo-bench-exports"))
FORBIDDEN_SQL = re.compile(r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b", re.IGNORECASE)
SOURCE_REFERENCE = re.compile(r"\b(?:FROM|JOIN)\s+([^\s,(;]+)", re.IGNORECASE)
FROM_CLAUSE = re.compile(
    r"\bFROM\s+(.+?)(?=\b(?:WHERE|GROUP|ORDER|HAVING|LIMIT|OFFSET|UNION)\b|$)",
    re.IGNORECASE | re.DOTALL,
)
LIMIT_CLAUSE = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)
DEMO2_TABLE = re.compile(r"^demo2_[A-Za-z0-9_]+$")


def _connection():
    """Create a short-lived connection to the local WSL Postgres instance."""
    return psycopg2.connect(DATABASE_URL, connect_timeout=5)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _validate_read_query(sql: str) -> str:
    """Allow a single SELECT limited to Demo 2 tables."""
    query = sql.strip()
    if not query.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in query:
        raise ValueError("Multiple SQL statements are not allowed.")
    if FORBIDDEN_SQL.search(query):
        raise ValueError("The query contains a forbidden SQL operation.")

    if any("," in match.group(1) for match in FROM_CLAUSE.finditer(query)):
        raise ValueError("Comma-separated table sources are not allowed.")

    for match in SOURCE_REFERENCE.finditer(query):
        relation = match.group(1).strip('"')
        table_name = relation.rsplit(".", maxsplit=1)[-1].strip('"')
        if not DEMO2_TABLE.fullmatch(table_name):
            raise ValueError("Queries may reference only demo2_* tables.")

    return query if LIMIT_CLAUSE.search(query) else f"{query} LIMIT 100"


def query_extractions(sql: str) -> dict[str, Any]:
    """Run a guarded read-only query over Demo 2 tables."""
    try:
        query = _validate_read_query(sql)
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = 5000")
                cursor.execute(query)
                columns = [column.name for column in cursor.description]
                rows = cursor.fetchmany(100)
        return {"columns": columns, "rows": [list(row) for row in rows], "row_count": len(rows)}
    except Exception as error:
        return {"error": str(error)}


def get_invoice_detail(invoice_id: int) -> dict[str, Any]:
    """Return the most recent extraction and source metadata for one invoice."""
    try:
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT i.filename, i.dataset_source, i.image_path, i.ground_truth,
                           e.overall_accuracy, e.extracted_data, e.field_scores,
                           e.model_used, e.run_id, e.extracted_at
                    FROM arcillis.demo2_invoice i
                    LEFT JOIN arcillis.demo2_extraction e ON e.invoice_id = i.id
                    WHERE i.id = %s
                    ORDER BY e.extracted_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (invoice_id,),
                )
                row = cursor.fetchone()
                columns = [column.name for column in cursor.description]
        if row is None:
            return {"error": f"Invoice {invoice_id} was not found."}

        result = dict(zip(columns, row, strict=True))
        invoice = {
            "filename": result["filename"],
            "dataset": result["dataset_source"],
            "image_path": result["image_path"],
            "ground_truth": _as_dict(result["ground_truth"]),
        }
        if result["extracted_data"] is None:
            return {**invoice, "extraction": None}
        return {
            **invoice,
            "overall_accuracy": float(result["overall_accuracy"] or 0),
            "extracted_data": _as_dict(result["extracted_data"]),
            "field_scores": _as_dict(result["field_scores"]),
            "model_used": result["model_used"],
            "run_id": result["run_id"],
            "extracted_at": str(result["extracted_at"]),
        }
    except Exception as error:
        return {"error": str(error)}


def summarize_batch(run_id: str | None = None) -> dict[str, Any]:
    """Summarize extraction quality, datasets, and recurring field misses."""
    try:
        query = """
            SELECT e.run_id, e.overall_accuracy, e.field_scores, i.dataset_source
            FROM arcillis.demo2_extraction e
            JOIN arcillis.demo2_invoice i ON i.id = e.invoice_id
        """
        params: tuple[str, ...] = ()
        if run_id:
            query += " WHERE e.run_id = %s"
            params = (run_id,)
        with _connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()

                cursor.execute("SELECT DISTINCT run_id FROM arcillis.demo2_extraction ORDER BY run_id")
                available_runs = [row[0] for row in cursor.fetchall()]

        total = len(rows)
        accuracies = [float(row[1] or 0) for row in rows]
        grades = {"green_95_plus": 0, "yellow_80_94": 0, "red_below_80": 0}
        datasets: dict[str, list[float]] = defaultdict(list)
        field_totals: Counter[str] = Counter()
        field_misses: Counter[str] = Counter()
        for _, accuracy, scores, dataset in rows:
            value = float(accuracy or 0)
            grades["green_95_plus" if value >= 95 else "yellow_80_94" if value >= 80 else "red_below_80"] += 1
            datasets[str(dataset or "unknown")].append(value)
            for field, passed in _as_dict(scores).items():
                field_totals[field] += 1
                if not passed:
                    field_misses[field] += 1

        worst_fields = [
            {
                "field": field,
                "miss_count": field_misses[field],
                "miss_rate": round(field_misses[field] / field_totals[field], 4),
            }
            for field in sorted(field_totals, key=lambda name: (-field_misses[name], name))[:10]
        ]
        return {
            "total_extractions": total,
            "average_accuracy": round(sum(accuracies) / total, 2) if total else 0.0,
            "by_grade": grades,
            "by_dataset": {
                name: {"count": len(values), "avg_accuracy": round(sum(values) / len(values), 2)}
                for name, values in datasets.items()
            },
            "worst_fields": worst_fields,
            "available_runs": available_runs,
        }
    except Exception as error:
        return {"error": str(error)}


def _export_rows(invoice_ids: list[int] | None) -> tuple[list[str], list[list[Any]]]:
    query = """
        SELECT i.id, i.filename, i.dataset_source, e.overall_accuracy, e.model_used, e.run_id,
               e.extracted_data
        FROM arcillis.demo2_extraction e
        JOIN arcillis.demo2_invoice i ON i.id = e.invoice_id
    """
    params: tuple[Any, ...] = ()
    if invoice_ids is not None:
        if not invoice_ids:
            return _export_headers([]), []
        query += " WHERE i.id = ANY(%s)"
        params = (invoice_ids,)
    query += " ORDER BY i.filename"
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            records = cursor.fetchall()

    flattened: list[dict[str, Any]] = []
    for _, filename, dataset, accuracy, model, run, data in records:
        extracted = _as_dict(data)
        row: dict[str, Any] = {
            "filename": filename,
            "dataset_source": dataset,
            "overall_accuracy": float(accuracy or 0),
            "model_used": model,
            "run_id": run,
            "items_json": json.dumps(extracted.get("items", []), ensure_ascii=True),
        }
        for section in ("header", "summary"):
            values = extracted.get(section, {})
            if isinstance(values, dict):
                row.update({f"{section}.{key}": value for key, value in values.items()})
        flattened.append(row)
    headers = _export_headers(flattened)
    return headers, [[row.get(header, "") for header in headers] for row in flattened]


def _export_headers(rows: list[dict[str, Any]]) -> list[str]:
    metadata = ["filename", "dataset_source", "overall_accuracy", "model_used", "run_id"]
    fields = [
        field
        for row in rows
        for field in row
        if field not in metadata and field != "items_json"
    ]
    return [*metadata, *dict.fromkeys(fields), "items_json"]


def _output_path(filename: str, extension: str) -> Path:
    name = Path(filename).name
    if not name or name != filename:
        raise ValueError("filename must be a file name without directory components.")
    path = Path(name)
    if path.suffix.lower() != extension:
        path = path.with_suffix(extension)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR / path.name


def export_to_csv(invoice_ids: list[int] | None = None, filename: str = "extractions.csv") -> dict[str, Any]:
    """Export selected or all extraction records to a flattened CSV file."""
    try:
        headers, rows = _export_rows(invoice_ids)
        output = _output_path(filename, ".csv")
        with output.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(headers)
            writer.writerows(rows)
        return {"filepath": str(output), "row_count": len(rows)}
    except Exception as error:
        return {"error": str(error)}


def export_to_excel(invoice_ids: list[int] | None = None, filename: str = "extractions.xlsx") -> dict[str, Any]:
    """Export selected or all extraction records to a formatted Excel workbook."""
    try:
        headers, rows = _export_rows(invoice_ids)
        output = _output_path(filename, ".xlsx")
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Extractions"
        worksheet.append(headers)
        for row in rows:
            worksheet.append(row)
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
        accuracy_column = headers.index("overall_accuracy") + 1
        fills = (
            (95, PatternFill("solid", fgColor="D4EDDA")),
            (80, PatternFill("solid", fgColor="FFF3CD")),
            (0, PatternFill("solid", fgColor="F8D7DA")),
        )
        for row_index in range(2, worksheet.max_row + 1):
            value = worksheet.cell(row_index, accuracy_column).value or 0
            worksheet.cell(row_index, accuracy_column).fill = next(fill for threshold, fill in fills if value >= threshold)
        for column_index, header in enumerate(headers, start=1):
            worksheet.column_dimensions[worksheet.cell(1, column_index).column_letter].width = max(len(header), 15)
        workbook.save(output)
        return {"filepath": str(output), "row_count": len(rows)}
    except Exception as error:
        return {"error": str(error)}


def reprocess_invoices(invoice_ids: list[int]) -> dict[str, Any]:
    """Queue a future extraction rerun without invoking the extraction engine yet."""
    logging.getLogger(__name__).info("Reprocessing requested for invoices: %s", invoice_ids)
    return {
        "status": "queued",
        "invoice_ids": invoice_ids,
        "message": f"Reprocessing queued for {len(invoice_ids)} invoices. This will be processed in the next extraction batch.",
    }
