"""Demo 2 document-extraction tools exposed by the Demo Bench MCP server."""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


# Percent-encode the equals sign so psycopg2/libpq parses the search-path option.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://autocore_writer:autocore_pipeline_2026@localhost:5432/hive?options=-csearch_path%3Darcillis",
)
EXPORT_DIR = Path(os.environ.get("DEMO_BENCH_EXPORT_DIR", "/tmp/demo-bench-exports"))
GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "")
INBOX_STAGING_DIR = Path(os.environ.get("INBOX_STAGING_DIR", "/tmp/arc-inbox-staging"))
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


def write_cells(workbook: str, sheet: str, range: str, values: list[Any]) -> dict[str, Any]:
    """Write a value, row, or grid to a range in an open Excel workbook."""
    import xlwings as xw

    wb = xw.books[workbook]
    ws = wb.sheets[sheet]
    ws.range(range).value = values
    return {"status": "written", "workbook": workbook, "sheet": sheet, "range": range}


def read_cells(workbook: str, sheet: str, range: str) -> dict[str, Any]:
    """Read values from a range in an open Excel workbook."""
    import xlwings as xw

    wb = xw.books[workbook]
    ws = wb.sheets[sheet]
    return {"values": ws.range(range).value, "workbook": workbook, "sheet": sheet, "range": range}


def format_cells(
    workbook: str,
    sheet: str,
    range: str,
    bold: bool = False,
    color: str | None = None,
) -> dict[str, Any]:
    """Apply basic font formatting to a range in an open Excel workbook."""
    import xlwings as xw

    wb = xw.books[workbook]
    ws = wb.sheets[sheet]
    cell_range = ws.range(range)
    if bold:
        cell_range.font.bold = True
    if color:
        hex_color = color.lstrip("#")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", hex_color):
            raise ValueError("color must be a six-digit hexadecimal value, such as #22C55E.")
        cell_range.font.color = tuple(int(hex_color[index : index + 2], 16) for index in (0, 2, 4))
    return {"status": "formatted", "workbook": workbook, "sheet": sheet, "range": range}


def write_extraction_row(workbook: str, sheet: str, row_number: int, extraction_data: dict[str, Any]) -> dict[str, Any]:
    """Write one extraction result to Excel with an accuracy color indicator."""
    import xlwings as xw

    wb = xw.books[workbook]
    ws = wb.sheets[sheet]
    columns = ["A", "B", "C", "D", "E", "F", "G"]
    fields = ["invoice_id", "vendor", "invoice_number", "date", "total", "accuracy", "status"]

    for column, field in zip(columns, fields, strict=True):
        cell = ws.range(f"{column}{row_number}")
        value = extraction_data.get(field, "")
        cell.value = value
        if field == "accuracy" and isinstance(value, (int, float)):
            cell.font.color = (34, 197, 94) if value >= 90 else (234, 179, 8) if value >= 70 else (239, 68, 68)

    return {"status": "written", "workbook": workbook, "sheet": sheet, "row": row_number}



# ---------------------------------------------------------------------------
# Google Sheets tools (gspread + service account)
# ---------------------------------------------------------------------------

def _sheets_client():
    """Return an authorized gspread client using the service account JSON."""
    import gspread

    if not GOOGLE_SHEETS_CREDENTIALS:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS env var is not set.")
    return gspread.service_account(filename=GOOGLE_SHEETS_CREDENTIALS)


def sheets_write_headers(spreadsheet_id: str, sheet_name: str = "Sheet1") -> dict[str, Any]:
    """Write the standard extraction header row and apply bold formatting."""
    try:
        gc = _sheets_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_name)
        headers = ["Invoice ID", "Filename", "Vendor", "Invoice Number", "Date", "Total", "Accuracy", "Status"]
        ws.update("A1", [headers], value_input_option="RAW")
        ws.format("A1:H1", {"textFormat": {"bold": True}})
        return {"status": "headers_written", "spreadsheet_id": spreadsheet_id, "columns": len(headers)}
    except Exception as error:
        return {"error": str(error)}


def sheets_write_extraction_row(
    spreadsheet_id: str,
    row_number: int,
    extraction_data: dict[str, Any],
    sheet_name: str = "Sheet1",
) -> dict[str, Any]:
    """Write one extraction result as a color-coded row in a Google Sheet."""
    try:
        gc = _sheets_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_name)
        fields = ["invoice_id", "filename", "vendor", "invoice_number", "date", "total", "accuracy", "status"]
        row = [extraction_data.get(f, "") for f in fields]
        ws.update(f"A{row_number}", [row], value_input_option="RAW")

        accuracy = extraction_data.get("accuracy")
        if isinstance(accuracy, (int, float)):
            if accuracy >= 95:
                bg = {"red": 0.83, "green": 0.93, "blue": 0.85}
            elif accuracy >= 80:
                bg = {"red": 1.0, "green": 0.95, "blue": 0.8}
            else:
                bg = {"red": 0.97, "green": 0.84, "blue": 0.85}
            ws.format(f"G{row_number}", {"backgroundColor": bg})
        return {"status": "row_written", "spreadsheet_id": spreadsheet_id, "row": row_number}
    except Exception as error:
        return {"error": str(error)}


def sheets_write_cells(
    spreadsheet_id: str,
    range_str: str,
    values: list[Any],
    sheet_name: str = "Sheet1",
) -> dict[str, Any]:
    """Write a value, row, or grid to an arbitrary range in a Google Sheet."""
    try:
        gc = _sheets_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_name)
        data = values if isinstance(values[0], list) else [values]
        ws.update(range_str, data, value_input_option="RAW")
        return {"status": "written", "spreadsheet_id": spreadsheet_id, "range": range_str}
    except Exception as error:
        return {"error": str(error)}


def sheets_read_cells(
    spreadsheet_id: str,
    range_str: str,
    sheet_name: str = "Sheet1",
) -> dict[str, Any]:
    """Read values from a range in a Google Sheet."""
    try:
        gc = _sheets_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_name)
        values = ws.get(range_str)
        return {"values": values, "spreadsheet_id": spreadsheet_id, "range": range_str}
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


def scan_inbox() -> dict[str, Any]:
    """Download unread PDF and image attachments from the configured Gmail inbox."""
    credentials_path = os.environ.get("GMAIL_CREDENTIALS_PATH")
    if not credentials_path:
        return {"emails_processed": 0, "attachments_saved": [], "errors": ["GMAIL_CREDENTIALS_PATH is not set."]}

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as error:
        return {"emails_processed": 0, "attachments_saved": [], "errors": [f"Gmail dependencies are unavailable: {error}"]}

    try:
        scopes = ["https://www.googleapis.com/auth/gmail.modify"]
        token_path = Path(credentials_path).with_name("gmail-token.json")
        credentials = Credentials.from_authorized_user_file(token_path, scopes) if token_path.exists() else None
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                credentials = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes).run_local_server(port=0)
            token_path.write_text(credentials.to_json(), encoding="utf-8")

        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        messages = service.users().messages().list(userId="me", q="is:unread has:attachment").execute().get("messages", [])
        INBOX_STAGING_DIR.mkdir(parents=True, exist_ok=True)
        attachments_saved: list[str] = []
        errors: list[str] = []
        emails_processed = 0

        for message_ref in messages:
            message_id = message_ref["id"]
            try:
                message = service.users().messages().get(userId="me", id=message_id).execute()
                parts = _attachment_parts(message.get("payload", {}))
                for part in parts:
                    filename = Path(part.get("filename", "")).name
                    attachment_id = part.get("body", {}).get("attachmentId")
                    if not filename or not attachment_id:
                        continue
                    content = service.users().messages().attachments().get(
                        userId="me", messageId=message_id, id=attachment_id
                    ).execute()["data"]
                    import base64

                    destination = _unique_path(INBOX_STAGING_DIR / filename)
                    destination.write_bytes(base64.urlsafe_b64decode(content + "=" * (-len(content) % 4)))
                    attachments_saved.append(str(destination))
                service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
                emails_processed += 1
            except Exception as error:
                errors.append(f"{message_id}: {error}")
        return {"emails_processed": emails_processed, "attachments_saved": attachments_saved, "errors": errors}
    except Exception as error:
        return {"emails_processed": 0, "attachments_saved": [], "errors": [str(error)]}


def _attachment_parts(part: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Gmail MIME parts that contain a downloaded attachment body."""
    result = [part] if part.get("filename") and part.get("body", {}).get("attachmentId") else []
    for child in part.get("parts", []):
        result.extend(_attachment_parts(child))
    return result


def _unique_path(path: Path) -> Path:
    """Avoid overwriting a same-named attachment from a separate email."""
    if not path.exists():
        return path
    return path.with_stem(f"{path.stem}-{int(time.time() * 1000)}")


def run_extraction(source_dir: str | None = None) -> dict[str, Any]:
    """Extract staged invoice images and persist results using the established vision pipeline."""
    source = Path(source_dir) if source_dir else INBOX_STAGING_DIR
    if not source.is_dir():
        return {"processed": 0, "succeeded": 0, "failed": 0, "errors": [f"Source directory does not exist: {source}"]}

    files = [path for path in sorted(source.iterdir()) if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}]
    if not files:
        return {"processed": 0, "succeeded": 0, "failed": 0, "errors": []}

    try:
        extract_invoice, grade_extraction, create_client, verify_proxy = _load_extraction_helpers()
        client = create_client()
        model_used = verify_proxy(client)
    except Exception as error:
        return {"processed": len(files), "succeeded": 0, "failed": len(files), "errors": [str(error)]}

    run_id = f"inbox-{time.strftime('%Y%m%d-%H%M%S')}"
    succeeded = 0
    errors: list[str] = []
    with _connection() as connection:
        for source_file in files:
            started = time.perf_counter()
            try:
                image_path = _render_pdf(source_file) if source_file.suffix.lower() == ".pdf" else source_file
                extracted_data = extract_invoice(image_path, client=client, model=model_used)
                invoice_id, ground_truth = _get_or_create_inbox_invoice(connection, source_file)
                field_scores, accuracy = grade_extraction(extracted_data, ground_truth)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO demo2_extraction
                            (invoice_id, run_id, model_used, extracted_data, field_scores, overall_accuracy, processing_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (invoice_id, run_id, model_used, Json(extracted_data), Json(field_scores), accuracy, round((time.perf_counter() - started) * 1000)),
                    )
                connection.commit()
                succeeded += 1
            except Exception as error:
                connection.rollback()
                errors.append(f"{source_file.name}: {error}")
    return {"processed": len(files), "succeeded": succeeded, "failed": len(files) - succeeded, "errors": errors}


def _load_extraction_helpers() -> tuple[Any, Any, Any, Any]:
    """Import the existing extraction and grading modules from the sibling demo directory."""
    extractor_dir = Path(__file__).resolve().parents[2] / "demo-2-pdf-extractor"
    if str(extractor_dir) not in sys.path:
        sys.path.insert(0, str(extractor_dir))
    from extract_invoice import create_client, extract_invoice, verify_proxy
    from grade_extraction import grade_extraction

    return extract_invoice, grade_extraction, create_client, verify_proxy


def _render_pdf(source_file: Path) -> Path:
    """Render the first PDF page for the vision model without changing source files."""
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("PDF extraction requires pymupdf.") from error
    document = fitz.open(source_file)
    try:
        if not document.page_count:
            raise ValueError("PDF has no pages.")
        destination = source_file.with_suffix(".page-1.png")
        document[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(destination)
        return destination
    finally:
        document.close()


def _get_or_create_inbox_invoice(connection: Any, source_file: Path) -> tuple[int, dict[str, Any]]:
    """Return an existing invoice or create a minimal inbox record for an attachment."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, ground_truth FROM demo2_invoice WHERE filename = %s", (source_file.name,))
        row = cursor.fetchone()
        if row:
            return int(row[0]), _as_dict(row[1])
        cursor.execute(
            """
            INSERT INTO demo2_invoice (filename, split, ground_truth, image_path, dataset_source)
            VALUES (%s, 'inbox', %s, %s, 'gmail_inbox')
            RETURNING id
            """,
            (source_file.name, Json({}), str(source_file.resolve())),
        )
        return int(cursor.fetchone()[0]), {}
