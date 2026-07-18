"""Demo-scoped MCP-style HTTP tool server for Arcillis Demo Bench.

Windows portproxy reference (do not run from this server):
netsh interface portproxy add v4tov4 listenport=8098 listenaddress=0.0.0.0 connectport=8098 connectaddress=<WSL_IP>
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from demo2_tools import (
    export_to_csv,
    export_to_excel,
    format_cells,
    get_invoice_detail,
    query_extractions,
    read_cells,
    reprocess_invoices,
    run_extraction,
    scan_inbox,
    sheets_append,
    sheets_calculate,
    sheets_clear,
    sheets_conditional_format,
    sheets_find,
    sheets_format_cells,
    sheets_manage,
    sheets_merge,
    sheets_read_cells,
    sheets_snapshot,
    sheets_validate,
    sheets_write_cells,
    sheets_write_extraction_row,
    sheets_write_headers,
    summarize_batch,
    write_cells,
    write_extraction_row,
)


@dataclass(frozen=True)
class Tool:
    """A callable tool and its OpenAI-compatible function metadata."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


TOOL_REGISTRY: dict[str, list[Tool]] = {
    "document_extractor": [
        Tool("query_extractions", "Run a guarded read-only SQL query against Demo 2 extraction tables.", _object({"sql": {"type": "string", "description": "A SELECT query over demo2_* tables."}}, ["sql"]), query_extractions),
        Tool("get_invoice_detail", "Get source and extraction details for one invoice.", _object({"invoice_id": {"type": "integer"}}, ["invoice_id"]), get_invoice_detail),
        Tool("summarize_batch", "Summarize extraction quality, datasets, and missed fields.", _object({"run_id": {"type": ["string", "null"], "description": "Optional extraction run ID."}}), summarize_batch),
        Tool("export_to_csv", "Export selected or all extraction results to CSV.", _object({"invoice_ids": {"type": ["array", "null"], "items": {"type": "integer"}}, "filename": {"type": "string"}}, ["filename"]), export_to_csv),
        Tool("export_to_excel", "Export selected or all extraction results to formatted Excel.", _object({"invoice_ids": {"type": ["array", "null"], "items": {"type": "integer"}}, "filename": {"type": "string"}}, ["filename"]), export_to_excel),
        Tool("reprocess_invoices", "Queue invoices for a future extraction rerun.", _object({"invoice_ids": {"type": "array", "items": {"type": "integer"}}}, ["invoice_ids"]), reprocess_invoices),
        Tool("scan_inbox", "Download unread PDF and image attachments from the configured Gmail inbox.", _object({}), scan_inbox),
        Tool("run_extraction", "Extract staged invoice images or PDFs and save the results.", _object({"source_dir": {"type": ["string", "null"], "description": "Optional staged attachment directory."}}), run_extraction),
        Tool("write_cells", "Write a value, row, or grid to a range in an already-open Excel workbook.", _object({"workbook": {"type": "string", "description": "Open workbook name, such as extractions.xlsx."}, "sheet": {"type": "string"}, "range": {"type": "string", "description": "Excel cell or range, such as A2 or A2:F2."}, "values": {"type": "array", "description": "Value list, row, or nested grid to write."}}, ["workbook", "sheet", "range", "values"]), write_cells),
        Tool("read_cells", "Read values from a range in an already-open Excel workbook.", _object({"workbook": {"type": "string"}, "sheet": {"type": "string"}, "range": {"type": "string"}}, ["workbook", "sheet", "range"]), read_cells),
        Tool("format_cells", "Apply bold font and/or a hexadecimal font color to cells in an open Excel workbook.", _object({"workbook": {"type": "string"}, "sheet": {"type": "string"}, "range": {"type": "string"}, "bold": {"type": "boolean", "default": False}, "color": {"type": ["string", "null"], "description": "Optional six-digit hex color, such as #22C55E."}}, ["workbook", "sheet", "range"]), format_cells),
        Tool("write_extraction_row", "Write one extraction result as a color-coded row in an open Excel workbook; use this for live row-by-row output.", _object({"workbook": {"type": "string"}, "sheet": {"type": "string"}, "row_number": {"type": "integer", "minimum": 1}, "extraction_data": {"type": "object", "description": "Extraction fields: invoice_id, vendor, invoice_number, date, total, accuracy, and status."}}, ["workbook", "sheet", "row_number", "extraction_data"]), write_extraction_row),
        Tool("sheets_write_headers", "Write a bold header row to a Google Sheet for extraction output.", _object({"spreadsheet_id": {"type": "string", "description": "Google Sheet ID from the URL."}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id"]), sheets_write_headers),
        Tool("sheets_write_extraction_row", "Write one extraction result as a color-coded row in a Google Sheet; use for live row-by-row output.", _object({"spreadsheet_id": {"type": "string"}, "row_number": {"type": "integer", "minimum": 2, "description": "Row number (2+ since row 1 is headers)."}, "extraction_data": {"type": "object", "description": "Fields: invoice_id, filename, vendor, invoice_number, date, total, accuracy, status."}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "row_number", "extraction_data"]), sheets_write_extraction_row),
        Tool("sheets_write_cells", "Write a value, row, or grid to an arbitrary range in a Google Sheet.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string", "description": "Cell or range like A2 or A2:F2."}, "values": {"type": "array"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "range_str", "values"]), sheets_write_cells),
        Tool("sheets_read_cells", "Read values from a range in a Google Sheet.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "range_str"]), sheets_read_cells),
        Tool("sheets_snapshot", "Get a compressed structural and data summary of a Google Sheet — headers, column types, fill rates, sample rows, issues, and optional formatting. Use this to see the sheet before reading or writing.", _object({
            "spreadsheet_id": {"type": "string", "description": "Google Sheet ID from the URL."},
            "sheet_name": {"type": "string", "default": "Sheet1"},
            "include_values": {"type": "boolean", "default": True, "description": "Include column analysis and sample rows."},
            "include_formatting": {"type": "boolean", "default": False, "description": "Include RLE-compressed formatting info."},
            "compact_mode": {"type": "boolean", "default": True, "description": "True = summary only (recommended). False = include all values."},
            "max_sample_rows": {"type": "integer", "default": 5, "description": "Number of sample rows from top and bottom."},
        }, ["spreadsheet_id"]), sheets_snapshot),
        Tool("sheets_format_cells", "Apply text, color, number, border, and column-width formatting to a Sheets range.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "bold": {"type": "boolean"}, "italic": {"type": "boolean"}, "font_color": {"type": "string"}, "background_color": {"type": "string"}, "font_size": {"type": "integer"}, "horizontal_alignment": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT"]}, "number_format": {"type": "string"}, "borders": {"type": "object"}, "column_width": {"type": "integer"}}, ["spreadsheet_id", "range_str"]), sheets_format_cells),
        Tool("sheets_calculate", "Evaluate a formula in a temporary Google Sheets cell.", _object({"spreadsheet_id": {"type": "string"}, "formula": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "formula"]), sheets_calculate),
        Tool("sheets_append", "Append one or more rows to a Google Sheet.", _object({"spreadsheet_id": {"type": "string"}, "values": {"type": "array"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "values"]), sheets_append),
        Tool("sheets_clear", "Clear values from a Sheets range without deleting its structure.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "range_str"]), sheets_clear),
        Tool("sheets_manage", "Insert or delete rows, or add, rename, and delete sheet tabs.", _object({"spreadsheet_id": {"type": "string"}, "operation": {"type": "string", "enum": ["insert_rows", "delete_rows", "add_sheet", "rename_sheet", "delete_sheet"]}, "sheet_name": {"type": "string", "default": "Sheet1"}, "row_index": {"type": "integer", "minimum": 1}, "num_rows": {"type": "integer", "minimum": 1, "default": 1}, "new_name": {"type": "string"}}, ["spreadsheet_id", "operation"]), sheets_manage),
        Tool("sheets_merge", "Merge or unmerge a Sheets range.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "merge_type": {"type": "string", "enum": ["MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS", "UNMERGE"], "default": "MERGE_ALL"}}, ["spreadsheet_id", "range_str"]), sheets_merge),
        Tool("sheets_find", "Find text across a Google Sheet.", _object({"spreadsheet_id": {"type": "string"}, "query": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "case_sensitive": {"type": "boolean", "default": False}}, ["spreadsheet_id", "query"]), sheets_find),
        Tool("sheets_conditional_format", "Add a conditional formatting rule to a Sheets range.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "rule_type": {"type": "string", "enum": ["NUMBER_LESS", "NUMBER_GREATER", "NUMBER_BETWEEN", "TEXT_CONTAINS", "TEXT_EQ", "CUSTOM_FORMULA"]}, "values": {"type": "array"}, "format": {"type": "object"}}, ["spreadsheet_id", "range_str", "rule_type", "values", "format"]), sheets_conditional_format),
        Tool("sheets_validate", "Set dropdown, checkbox, numeric, or formula validation on a Sheets range.", _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "validation_type": {"type": "string", "enum": ["ONE_OF_LIST", "CHECKBOX", "NUMBER_BETWEEN", "NUMBER_GREATER", "NUMBER_LESS", "CUSTOM_FORMULA"]}, "values": {"type": "array"}, "strict": {"type": "boolean", "default": True}, "show_dropdown": {"type": "boolean", "default": True}}, ["spreadsheet_id", "range_str", "validation_type"]), sheets_validate),
    ],
}


class ToolListRequest(BaseModel):
    demo: str


class ToolCallRequest(BaseModel):
    demo: str
    tool: str
    args: dict[str, Any] = {}


app = FastAPI(title="Demo Bench MCP Server")


def _tools_for(demo: str) -> list[Tool]:
    try:
        return TOOL_REGISTRY[demo]
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Unknown demo: {demo}") from error


@app.post("/mcp/tools/list")
def list_tools(request: ToolListRequest) -> list[dict[str, Any]]:
    """Return only the function definitions assigned to the requested demo."""
    return [tool.definition() for tool in _tools_for(request.demo)]


@app.post("/mcp/tools/call")
def call_tool(request: ToolCallRequest) -> dict[str, Any]:
    """Invoke a known demo-scoped tool with validated JSON arguments."""
    tool = next((item for item in _tools_for(request.demo) if item.name == request.tool), None)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool for {request.demo}: {request.tool}")
    try:
        return tool.handler(**request.args)
    except TypeError as error:
        raise HTTPException(status_code=422, detail=f"Invalid arguments for {request.tool}: {error}") from error
