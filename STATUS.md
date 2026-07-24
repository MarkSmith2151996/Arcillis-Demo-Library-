# Arcillis Demo Library Status

## Project

- Custodian project: `arcillis-demo-library`
- Stack: Python + PySide6 + FastAPI + DeepSeek API + Postgres + Google Sheets API + ChromaDB + Tauri v2 (arc-toolbar)
- Current state: Demo 2 extraction pipeline, MCP tools, and the ARC Toolbar's server-hosted PydanticAI SSE chat with multi-turn sessions are implemented. The local vision proxy and Gmail OAuth credentials must be configured before live intake/extraction tests.
- Next: Start the OpenCode proxy and Demo Bench MCP server with `DEEPSEEK_API_KEY`, configure Gmail OAuth, then run a staged-image and inbox smoke test.

## Architecture

- `arc-toolbar/`: Tauri v2 + Vite vanilla JS floating desktop app. It has three layout modes (Nokia, Strip, Chat-first), a custom title bar, admin settings overlay, and an SSE client for the server-hosted PydanticAI agent.
- `demo-bench/`: A standalone PySide6 desktop shell for client-facing Arcillis demos. A landing dialog selects a demo before its plugin supplies dockable document intake, source browsing, viewing, and batch-status widgets for Demo 2.

## File Map

- `arc-toolbar/index.html`: Vite entry point — root HTML shell with layout containers and Tabler Icons CDN.
- `arc-toolbar/src/main.js`: Toolbar state and layout engine, server health check, SSE agent chat consumer with ephemeral session IDs, tool-call display updates, display persistence, window sizing, admin settings, reset shortcut, and Tauri window controls.
- `arc-toolbar/src/components.js`: DOM-only renderer for the number, text, table, status, progress, button, and divider display primitives.
- `arc-toolbar/src-tauri/capabilities/default.json`: Tauri v2 permissions for drag, minimize, close, resizing, and always-on-top operations.
- `arc-toolbar/src/style.css`: Dark theme with CSS custom properties, three layout modes, custom titlebar, and admin overlay styles.
- `arc-toolbar/src-tauri/src/main.rs`: Minimal Tauri binary entry point delegating to lib.
- `arc-toolbar/src-tauri/src/lib.rs`: Tauri v2 builder with generate_context!().
- `arc-toolbar/src-tauri/tauri.conf.json`: Window config — 280x480, decorations false, alwaysOnTop true, transparent true.
- `demo-bench/main.py`: Application shell, landing dialog launch, dock-layout reset, dark palette, and connection status indicator.
- `demo-bench/widgets/demo_selector_window.py`: Dark landing dialog and clickable Document Extractor demo card.
- `demo-bench/plugins/document_extractor.py`: Registers and lays out the Document Extractor intake, viewer, batch status, results table, and export docks.
- `demo-bench/mcp_server/`: FastAPI server on port 8098 with demo-scoped MCP-style tool discovery/calls, guarded read access, result summaries, CSV/Excel exports, live xlwings workbook tools, Gmail inbox scanning, staged vision extraction, and a streaming PydanticAI agent endpoint with bounded in-memory multi-turn sessions. `start_mac.sh` connects to the PC Postgres instance through Tailscale.
- `demo-bench/mcp_server/agent.py`: PydanticAI DeepSeek harness with session-cached dynamic tool schemas, per-demo database schema hints, schema-backed local MCP wrappers, two-phase `load_tools` discovery, and a history-aware event-stream helper.
- `demo-bench/widgets/chat_widget.py`: Floating assistant bubble that discovers Demo 2 tools, calls DeepSeek from worker threads, and emits local invoice-highlight requests.
- `demo-bench/widgets/results_table_widget.py`: Loads extraction records, grades, selectable rows, and field-level comparisons from Postgres.
- `demo-bench/widgets/export_widget.py`: Exports checked (or confirmed all) extraction records as CSV or formatted Excel.
- `demo-bench/widgets/`: Intake, lazy thumbnail browser, document viewer, batch-status, results-table, and export components.

## Last 10 Changes

- 2026-07-24: Baked in the Mac-local stability fixes: FastAPI CORS middleware, PydanticAI 2.13-compatible agent imports and prompt replacement, Vite `/agent` and `/mcp` proxying, resilient display rendering, and a valid Tauri toolbar icon.
- 2026-07-22: Cached dynamically loaded MCP schemas with each agent session, supplied a Document Extractor database schema hint in runtime instructions, and verified PydanticAI 1.97.0 executes same-turn function calls in parallel by default.
- 2026-07-19: Replaced fragile free-text display JSON parsing with an `update_display` PydanticAI tool. The toolbar now renders validated display payloads directly from `tool_call` SSE events, while agent chat responses remain conversational text.
- 2026-07-19: Added safe lightweight Markdown rendering for completed ARC Toolbar assistant bubbles (bold, lists, and line breaks), while keeping user and typing content plain text. Added agent chat-format rules that reserve structured dashboards for display JSON and corrected the display JSON example so runtime prompt interpolation succeeds.
- 2026-07-18: Rewired ARC Toolbar chat to consume the PydanticAI SSE endpoint instead of calling DeepSeek and MCP tools directly. Added bounded in-memory multi-turn sessions, session reset, streamed typing/tool activity, and preserved structured toolbar display responses server-side.
- 2026-07-18: Added a PydanticAI DeepSeek agent harness with true two-phase MCP tool loading, enriched schemas for all 28 tools, `/mcp/tools/load`, and `/agent/chat` SSE events for text, tool calls, tool results, and completion.
- 2026-07-18: Corrected Google Sheets chart API payloads: BAR series now target `BOTTOM_AXIS`, PIE creation sends a single `ChartData` series, and PIE snapshots parse that singular structure.
- 2026-07-17: Added `sheets_chart_create` and `sheets_chart_snapshot` MCP tools for embedded BAR, LINE, PIE, COLUMN, and AREA Google Sheets charts plus readable chart verification snapshots.
- 2026-07-17: Added nine general-purpose Google Sheets MCP tools for formatting, formulas, row append/clear/management, merging, find, conditional formatting, and data validation. Added a live service-account smoke-test script and registered every tool under `document_extractor`.
- 2026-07-17: Fixed `sheets_snapshot` to detect and analyze only the Google Sheet's populated row and column range, while retaining the full grid dimensions for context.

## Known Issues

- The local OpenCode vision proxy on port 4096 must be running and compatible with the configured model before `run_extraction` can process staged files.
- `scan_inbox` needs a valid `GMAIL_CREDENTIALS_PATH`; its first run opens a local OAuth consent flow and stores `gmail-token.json` beside those credentials.
- The Mac bridge timed out during this task, so `start_mac.sh` and real Excel automation still need a manual macOS verification with an open workbook.
- The Google Sheets extension smoke test requires a service-account credential and a spreadsheet shared with that account; it was syntax and import verified locally but not run against the live API from this Linux workspace.
- This Linux workspace does not currently have `gspread`, so the chart tools were syntax and mocked API verified but need direct import verification in the dependency-complete MCP environment.
- The task specified PydanticAI 2.13.0, but the available global runtime has 1.97.0 and the root `.venv` lacks PydanticAI and FastAPI. The harness uses the documented 1.97 dynamic-tool API and was import verified there; deploy it with a runtime that includes PydanticAI.
