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
    get_invoice_detail,
    query_extractions,
    reprocess_invoices,
    summarize_batch,
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
