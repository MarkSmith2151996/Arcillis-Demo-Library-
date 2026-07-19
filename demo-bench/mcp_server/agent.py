"""PydanticAI harness for the Demo Bench document-extractor tools."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic_ai import Agent, AgentEventStream, FunctionToolset, RunContext, Tool
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider


MCP_URL = os.environ.get("DEMO_BENCH_MCP_URL", "http://localhost:8098/mcp/tools/call")
DEFAULT_CLIENT_NAME = "Test Client"
DEFAULT_SPREADSHEET_ID = os.environ.get("ARCILLIS_SPREADSHEET_ID", "test-sheet-id")
DEFAULT_DEMO_NAME = "document_extractor"


SYSTEM_PROMPT_TEMPLATE = """You are an AI operations specialist deployed by Arcillis. You are embedded in a client's desktop toolbar and your job is to process documents, manage spreadsheets, analyze extraction results, and deliver formatted output.

Client: {client_name}
Active Spreadsheet: {spreadsheet_id}
Active Demo: {demo_name}

AVAILABLE TOOLS

You have access to the following tools. Review this catalog to determine which tools you need for a task, then call load_tools with the tool names to load their full schemas before use.

--- Extraction Pipeline ---

scan_inbox - Download unread PDF and image attachments from the configured Gmail inbox. Creates staged files ready for extraction. Run this first when a client sends documents via email.

run_extraction - Run the AI extraction engine on staged invoice images or PDFs. Reads the document, pulls structured fields (vendor, date, amounts, line items), and saves results to the database.

query_extractions - Run a read-only SQL query against the extraction results tables. Use to inspect, filter, or aggregate extraction data by run_id, accuracy score, vendor, date range, or any extracted field.

get_invoice_detail - Get the full extraction result and source metadata for a single invoice by ID. Returns every extracted field, accuracy score, source filename, and dataset origin.

summarize_batch - Get a quality summary across all extractions or one run: total count, average accuracy, field coverage, common missed fields, dataset breakdown. Use for client confidence reporting.

reprocess_invoices - Queue specific invoices for re-extraction. Flags them for the next run. Does not execute extraction immediately.

--- Excel Output ---

write_cells - Write a value, row, or grid to a range in an already-open Excel workbook.

read_cells - Read values from a range in an already-open Excel workbook.

format_cells - Apply bold font and/or hex font color to cells in an open Excel workbook.

write_extraction_row - Write one extraction result as a color-coded row in Excel. Accuracy cell is colored green/yellow/red automatically.

export_to_csv - Export extraction results to a downloadable CSV file.

export_to_excel - Export extraction results to a formatted Excel file with bold headers, auto-width columns, and alternating row colors.

--- Google Sheets: General ---

sheets_snapshot - Get a compressed structural summary of a Google Sheet: dimensions, headers, column types, fill rates, sample rows, and issues.

sheets_read_cells - Read values from any range in a Google Sheet using A1 notation.

sheets_write_cells - Write a value, row, or grid to any range in a Google Sheet. Overwrites existing content.

sheets_format_cells - Apply formatting to a Sheets range: bold, italic, font color, background color, font size, alignment, number format, borders, and column width.

sheets_calculate - Evaluate any spreadsheet formula using Google Sheets as the computation engine. Returns the deterministic result.

sheets_append - Append rows to the bottom of the data in a sheet. Finds the last row automatically.

sheets_clear - Clear values from a range without deleting rows, columns, or formatting.

sheets_manage - Structural operations: insert rows, delete rows, add tabs, rename tabs, delete tabs.

sheets_merge - Merge or unmerge a range of cells. Use for title rows and section headers.

sheets_find - Search the entire sheet for text matches. Returns matching cells with A1 addresses.

sheets_conditional_format - Add a rules-based formatting rule to a range that persists on new data.

sheets_validate - Add dropdowns, checkboxes, or numeric constraints to a range.

sheets_chart_create - Create an embedded chart: BAR, COLUMN, LINE, PIE, or AREA.

sheets_chart_snapshot - List all embedded charts with type, title, data ranges, and position.

--- Google Sheets: Extraction-Specific ---

sheets_write_headers - Write a pre-formatted bold header row for extraction output. One-call setup.

sheets_write_extraction_row - Write one extraction result as a color-coded row. Accuracy is colored green/yellow/red automatically.

OPERATING RULES

1. Call load_tools before using any tool. You cannot call a tool without loading its full schema first.
2. Always call sheets_snapshot before modifying any Google Sheet. Understand the layout before you act.
3. Never perform arithmetic yourself. Use sheets_calculate for any computation - it is deterministic.
4. When a task requires multiple tools, plan the full sequence before executing. Write data before formatting it. Format before charting. Snapshot after major changes to verify.
5. If a tool returns an error, read the error message, adjust your parameters, and retry. Do not ask the user to fix it.
6. Report results with specifics: "Wrote 13 rows to A2:F14, average accuracy 91.3%." Not "Done."
7. Do not explain what you are about to do at length. State the action briefly, execute, report the outcome.
8. If the user's request is ambiguous, ask one clarifying question. Do not guess at critical parameters like which spreadsheet or which data range.
9. When creating formatted output, apply professional styling: bold headers with a dark background and white text, consistent number formatting, conditional coloring on accuracy scores.
10. Verify your work. After writing data, snapshot or read back to confirm. After creating a chart, snapshot it.
11. When a dashboard would make the response clearer, return exactly one JSON object without markdown. Its shape is {{"text":"brief chat summary","display":{{"size":{{"width":"compact|standard|wide|full","height":"short|standard|tall|full"}},"rows":[{{"components":[...]}}]}}}}. The display component types are number(value,label,color), text(value,label), table(headers,rows), status(label,value,color), progress(label,value,max,color), button(label,intent,color), and divider. Components may set width to full, half, or third. Use semantic colors success, warning, danger, neutral, info, or a hex color. Return plain text when a visual display is not useful.

CHAT FORMATTING RULES:
- Chat responses are short and conversational. You are talking in a narrow toolbar window.
- Use **bold** for emphasis on key numbers or terms.
- Use short bulleted lists (- item) when listing 2-5 items.
- Use numbered lists (1. item) for sequential steps.
- Do NOT use ## headers, markdown tables, code blocks, horizontal rules, or blockquotes in chat.
- Do NOT try to build dashboards or data tables in chat text - use the display JSON system for any structured data.
- Keep chat responses under 4-5 sentences unless the user asked a detailed question.
- If you have both a conversational answer AND structured data to show, put the conversational part in your text response and the structured data in a display JSON block.
"""


@dataclass
class AgentContext:
    """Per-run context that keeps dynamically loaded tools isolated per request."""

    client_name: str = DEFAULT_CLIENT_NAME
    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID
    demo_name: str = DEFAULT_DEMO_NAME
    loaded_tools: set[str] = field(default_factory=set)


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    guidance: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{description}\n\nGuidance:\n{guidance}",
        "parameters": parameters,
    }


# These schemas mirror the demo-scoped registry in server.py. Keeping them free
# of server imports lets `from agent import agent` work before optional MCP tools
# such as gspread are installed.
MCP_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    _tool(
        "query_extractions",
        "Run a guarded read-only SQL query against Demo 2 extraction tables.",
        _object({"sql": {"type": "string", "description": "A SELECT query over demo2_* tables."}}, ["sql"]),
        "Use SELECT statements only. Filter by run, vendor, date, or accuracy and include only the fields needed. The server limits results to 100 rows.",
    ),
    _tool(
        "get_invoice_detail",
        "Get source and extraction details for one invoice.",
        _object({"invoice_id": {"type": "integer"}}, ["invoice_id"]),
        "Use after query_extractions identifies a record that needs field-level inspection. Report the returned source metadata and accuracy precisely.",
    ),
    _tool(
        "summarize_batch",
        "Summarize extraction quality, datasets, and missed fields.",
        _object({"run_id": {"type": ["string", "null"], "description": "Optional extraction run ID."}}),
        "Use with a run_id for a single batch or omit it for the full dataset. Cite total count, average accuracy, and recurring misses in the final report.",
    ),
    _tool(
        "export_to_csv",
        "Export selected or all extraction results to CSV.",
        _object({"invoice_ids": {"type": ["array", "null"], "items": {"type": "integer"}}, "filename": {"type": "string"}}, ["filename"]),
        "Use a descriptive filename ending in .csv. Provide invoice_ids only when the client asked for a subset; otherwise export all matching results.",
    ),
    _tool(
        "export_to_excel",
        "Export selected or all extraction results to formatted Excel.",
        _object({"invoice_ids": {"type": ["array", "null"], "items": {"type": "integer"}}, "filename": {"type": "string"}}, ["filename"]),
        "Use when a formatted client workbook is needed. The export applies bold headers, widths, and accuracy coloring; report the returned file path and row count.",
    ),
    _tool(
        "reprocess_invoices",
        "Queue invoices for a future extraction rerun.",
        _object({"invoice_ids": {"type": "array", "items": {"type": "integer"}}}, ["invoice_ids"]),
        "Queue only the requested invoice IDs. This does not immediately run extraction, so make that distinction clear to the client.",
    ),
    _tool(
        "scan_inbox",
        "Download unread PDF and image attachments from the configured Gmail inbox.",
        _object({}),
        "Run first when documents arrived through email. Inspect attachments_saved and errors before starting extraction.",
    ),
    _tool(
        "run_extraction",
        "Extract staged invoice images or PDFs and save the results.",
        _object({"source_dir": {"type": ["string", "null"], "description": "Optional staged attachment directory."}}),
        "Run after scan_inbox or when the client supplied a known staging directory. Follow it with summarize_batch or query_extractions to verify results.",
    ),
    _tool(
        "write_cells",
        "Write a value, row, or grid to a range in an already-open Excel workbook.",
        _object({"workbook": {"type": "string", "description": "Open workbook name, such as extractions.xlsx."}, "sheet": {"type": "string"}, "range": {"type": "string", "description": "Excel cell or range, such as A2 or A2:F2."}, "values": {"type": "array", "description": "Value list, row, or nested grid to write."}}, ["workbook", "sheet", "range", "values"]),
        "Confirm the workbook and sheet names first. Write all related values in one grid call, then read the range back before reporting success.",
    ),
    _tool(
        "read_cells",
        "Read values from a range in an already-open Excel workbook.",
        _object({"workbook": {"type": "string"}, "sheet": {"type": "string"}, "range": {"type": "string"}}, ["workbook", "sheet", "range"]),
        "Use before editing an existing Excel range and after writes to verify the final values. Use a focused range rather than reading a full workbook.",
    ),
    _tool(
        "format_cells",
        "Apply bold font and/or a hexadecimal font color to cells in an open Excel workbook.",
        _object({"workbook": {"type": "string"}, "sheet": {"type": "string"}, "range": {"type": "string"}, "bold": {"type": "boolean", "default": False}, "color": {"type": ["string", "null"], "description": "Optional six-digit hex color, such as #22C55E."}}, ["workbook", "sheet", "range"]),
        "Write values before formatting. Supply hex colors with # and combine bold and color in one call when both are needed.",
    ),
    _tool(
        "write_extraction_row",
        "Write one extraction result as a color-coded row in an open Excel workbook; use this for live row-by-row output.",
        _object({"workbook": {"type": "string"}, "sheet": {"type": "string"}, "row_number": {"type": "integer", "minimum": 1}, "extraction_data": {"type": "object", "description": "Extraction fields: invoice_id, vendor, invoice_number, date, total, accuracy, and status."}}, ["workbook", "sheet", "row_number", "extraction_data"]),
        "Use after headers exist. Include all extraction fields and let the tool apply its accuracy color. Read the row back if a client needs confirmation.",
    ),
    _tool(
        "sheets_write_headers",
        "Write a bold header row to a Google Sheet for extraction output.",
        _object({"spreadsheet_id": {"type": "string", "description": "Google Sheet ID from the URL."}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id"]),
        "Snapshot the sheet first. Use once before writing extraction rows, then verify the header range with sheets_read_cells.",
    ),
    _tool(
        "sheets_write_extraction_row",
        "Write one extraction result as a color-coded row in a Google Sheet; use for live row-by-row output.",
        _object({"spreadsheet_id": {"type": "string"}, "row_number": {"type": "integer", "minimum": 2, "description": "Row number (2+ since row 1 is headers)."}, "extraction_data": {"type": "object", "description": "Fields: invoice_id, filename, vendor, invoice_number, date, total, accuracy, status."}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "row_number", "extraction_data"]),
        "Snapshot before editing and write headers first. Accuracy is color-coded automatically; read the row back after writing a client-facing result.",
    ),
    _tool(
        "sheets_write_cells",
        "Write a value, row, or grid to an arbitrary range in a Google Sheet.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string", "description": "Cell or range like A2 or A2:F2."}, "values": {"type": "array"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "range_str", "values"]),
        "Always snapshot first. Write one related grid at a time, preserve the existing layout, and read or snapshot the range after the write.",
    ),
    _tool(
        "sheets_read_cells",
        "Read values from a range in a Google Sheet.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "range_str"]),
        "Use A1 notation and narrow ranges to the information needed. Use it to verify writes after the initial structural snapshot.",
    ),
    _tool(
        "sheets_snapshot",
        "Get a compressed structural and data summary of a Google Sheet - headers, column types, fill rates, sample rows, issues, and optional formatting.",
        _object({"spreadsheet_id": {"type": "string", "description": "Google Sheet ID from the URL."}, "sheet_name": {"type": "string", "default": "Sheet1"}, "include_values": {"type": "boolean", "default": True, "description": "Include column analysis and sample rows."}, "include_formatting": {"type": "boolean", "default": False, "description": "Include RLE-compressed formatting info."}, "compact_mode": {"type": "boolean", "default": True, "description": "True = summary only (recommended). False = include all values."}, "max_sample_rows": {"type": "integer", "default": 5, "description": "Number of sample rows from top and bottom."}}, ["spreadsheet_id"]),
        "Call before every Sheets modification. Keep compact_mode true unless the full values are necessary, and request formatting only when styling affects the task.",
    ),
    _tool(
        "sheets_chart_create",
        "Create an embedded chart (bar, line, pie, column, area) in a Google Sheet.",
        _object({"spreadsheet_id": {"type": "string"}, "chart_type": {"type": "string", "enum": ["BAR", "LINE", "PIE", "COLUMN", "AREA"]}, "label_range": {"type": "string", "description": "A1 range for x-axis / pie labels, e.g. A3:A15"}, "data_ranges": {"type": "array", "items": {"type": "string"}, "description": "A1 ranges for each data series"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "series_names": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"}, "anchor_cell": {"type": "string", "default": "H2"}, "width": {"type": "integer", "default": 600}, "height": {"type": "integer", "default": 400}}, ["spreadsheet_id", "chart_type", "label_range", "data_ranges"]),
        "Snapshot first and create the chart only after data and formatting are complete. Use matching label/data ranges, a descriptive title, and verify with sheets_chart_snapshot.",
    ),
    _tool(
        "sheets_chart_snapshot",
        "List all embedded charts in a sheet with type, data ranges, title, and position.",
        _object({"spreadsheet_id": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id"]),
        "Use after chart creation to confirm chart type, ranges, title, and placement. Report those specifics rather than simply saying a chart exists.",
    ),
    _tool(
        "sheets_format_cells",
        "Apply text, color, number, border, and column-width formatting to a Sheets range.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "bold": {"type": "boolean"}, "italic": {"type": "boolean"}, "font_color": {"type": "string"}, "background_color": {"type": "string"}, "font_size": {"type": "integer"}, "horizontal_alignment": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT"]}, "number_format": {"type": "string"}, "borders": {"type": "object"}, "column_width": {"type": "integer"}}, ["spreadsheet_id", "range_str"]),
        "Snapshot first and combine format properties in one call. Hex colors require #; use Sheets patterns such as #,##0.00, 0.0%, and $#,##0.00. Format only after data is written.",
    ),
    _tool(
        "sheets_calculate",
        "Evaluate a formula in a temporary Google Sheets cell.",
        _object({"spreadsheet_id": {"type": "string"}, "formula": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "formula"]),
        "Use for every arithmetic or aggregate instead of calculating mentally. Pass a normal Sheets formula; the tool adds a leading = when needed and clears its temporary cell.",
    ),
    _tool(
        "sheets_append",
        "Append one or more rows to a Google Sheet.",
        _object({"spreadsheet_id": {"type": "string"}, "values": {"type": "array"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "values"]),
        "Snapshot first to confirm the table structure. Supply a row or grid of rows; the tool finds the bottom automatically. Snapshot or read back after appending.",
    ),
    _tool(
        "sheets_clear",
        "Clear values from a range without deleting its rows or columns.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}}, ["spreadsheet_id", "range_str"]),
        "Snapshot first and target the smallest correct range. This preserves formatting and structure, so use sheets_manage only when a structural change is requested.",
    ),
    _tool(
        "sheets_manage",
        "Insert or delete rows, or add, rename, and delete sheet tabs.",
        _object({"spreadsheet_id": {"type": "string"}, "operation": {"type": "string", "enum": ["insert_rows", "delete_rows", "add_sheet", "rename_sheet", "delete_sheet"]}, "sheet_name": {"type": "string", "default": "Sheet1"}, "row_index": {"type": "integer", "minimum": 1}, "num_rows": {"type": "integer", "minimum": 1, "default": 1}, "new_name": {"type": "string"}}, ["spreadsheet_id", "operation"]),
        "Snapshot first. Require row_index for row operations and new_name for add or rename. Confirm destructive delete operations match the client request before executing.",
    ),
    _tool(
        "sheets_merge",
        "Merge or unmerge a Sheets range.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "merge_type": {"type": "string", "enum": ["MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS", "UNMERGE"], "default": "MERGE_ALL"}}, ["spreadsheet_id", "range_str"]),
        "Snapshot first. Use merges for titles and section headers only, and use UNMERGE when restoring a range. Verify the merged layout afterward.",
    ),
    _tool(
        "sheets_find",
        "Find text across a Google Sheet.",
        _object({"spreadsheet_id": {"type": "string"}, "query": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "case_sensitive": {"type": "boolean", "default": False}}, ["spreadsheet_id", "query"]),
        "Use before edits when the client refers to text rather than a known cell. The results include A1 addresses; choose the exact target before writing.",
    ),
    _tool(
        "sheets_conditional_format",
        "Add a conditional formatting rule to a Sheets range.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "rule_type": {"type": "string", "enum": ["NUMBER_LESS", "NUMBER_GREATER", "NUMBER_BETWEEN", "TEXT_CONTAINS", "TEXT_EQ", "CUSTOM_FORMULA"]}, "values": {"type": "array"}, "format": {"type": "object"}}, ["spreadsheet_id", "range_str", "rule_type", "values", "format"]),
        "Snapshot first. Use values in rule order, and set format with background_color, font_color, and/or bold. The rule persists for future data, so scope the range carefully.",
    ),
    _tool(
        "sheets_validate",
        "Set dropdown, checkbox, number, or formula validation on a Sheets range.",
        _object({"spreadsheet_id": {"type": "string"}, "range_str": {"type": "string"}, "sheet_name": {"type": "string", "default": "Sheet1"}, "validation_type": {"type": "string", "enum": ["ONE_OF_LIST", "CHECKBOX", "NUMBER_BETWEEN", "NUMBER_GREATER", "NUMBER_LESS", "CUSTOM_FORMULA"]}, "values": {"type": "array"}, "strict": {"type": "boolean", "default": True}, "show_dropdown": {"type": "boolean", "default": True}}, ["spreadsheet_id", "range_str", "validation_type"]),
        "Snapshot first. Use ONE_OF_LIST values for dropdown choices, CHECKBOX without values, and numeric or formula values in the expected order. Keep strict true unless the client requests warnings only.",
    ),
)

MCP_TOOLS_BY_NAME = {tool["name"]: tool for tool in MCP_TOOL_SPECS}


def get_tool_definitions(names: list[str]) -> list[dict[str, Any]]:
    """Return enriched MCP schemas for the requested tools."""
    requested = list(dict.fromkeys(names))
    unknown = [name for name in requested if name not in MCP_TOOLS_BY_NAME]
    if unknown:
        raise ValueError(f"Unknown MCP tools: {', '.join(unknown)}")
    return [copy.deepcopy(MCP_TOOLS_BY_NAME[name]) for name in requested]


def make_mcp_tool(spec: dict[str, Any]) -> Tool[AgentContext]:
    """Create a schema-backed tool that forwards calls to the local MCP server."""

    async def call_mcp_tool(ctx: RunContext[AgentContext], **kwargs: Any) -> str:
        payload = {"demo": ctx.deps.demo_name, "tool": spec["name"], "args": kwargs}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(MCP_URL, json=payload)
            return response.text
        except httpx.HTTPError as error:
            return json.dumps({"error": f"MCP request failed: {error}"})

    return Tool.from_schema(
        function=call_mcp_tool,
        name=spec["name"],
        description=spec["description"],
        json_schema=spec["parameters"],
        takes_ctx=True,
    )


MCP_TOOLS = {name: make_mcp_tool(spec) for name, spec in MCP_TOOLS_BY_NAME.items()}


async def load_tools(ctx: RunContext[AgentContext], tools: list[str]) -> str:
    """Load full schemas for requested MCP tools before using them."""
    try:
        definitions = get_tool_definitions(tools)
    except ValueError as error:
        return json.dumps({"error": str(error), "available_tools": list(MCP_TOOLS_BY_NAME)})

    ctx.deps.loaded_tools.update(definition["name"] for definition in definitions)
    return json.dumps({"loaded_tools": definitions})


def _runtime_instructions(ctx: RunContext[AgentContext]) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        client_name=ctx.deps.client_name,
        spreadsheet_id=ctx.deps.spreadsheet_id,
        demo_name=ctx.deps.demo_name,
    )


agent = Agent[AgentContext, str](
    deps_type=AgentContext,
    instructions=_runtime_instructions,
    tools=[load_tools],
    tool_timeout=60,
)


def run_agent_events(
    message: str,
    context: AgentContext,
    model: OpenAIChatModel,
    message_history: list[Any] | None = None,
) -> AgentEventStream[Any]:
    """Start an event stream while preserving an optional prior conversation."""
    return agent.run_stream_events(
        message,
        deps=context,
        model=model,
        message_history=message_history,
    )


@agent.toolset
def loaded_mcp_toolset(ctx: RunContext[AgentContext]) -> FunctionToolset[AgentContext]:
    """Expose only tools selected by load_tools on the next model turn."""
    tools = [MCP_TOOLS[spec["name"]] for spec in MCP_TOOL_SPECS if spec["name"] in ctx.deps.loaded_tools]
    return FunctionToolset(tools=tools)


def get_model() -> OpenAIChatModel:
    """Build the DeepSeek model lazily so imports do not require credentials."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY must be set before starting an agent chat.")
    return OpenAIChatModel(
        "deepseek-v4-flash",
        provider=DeepSeekProvider(api_key=api_key),
    )
