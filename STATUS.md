# Arcillis Demo Library Status

## Project

- Custodian project: `arcillis-demo-library`
- Stack: Python + PySide6 + FastAPI + DeepSeek API + Postgres + Google Sheets API + ChromaDB + Tauri v2 (arc-toolbar)
- Current state: Demo 2 extraction pipeline, MCP tools, and the ARC Toolbar's DeepSeek/MCP chat loop are implemented. The local vision proxy and Gmail OAuth credentials must be configured before live intake/extraction tests.
- Next: Start the OpenCode proxy and Demo Bench MCP server, set `VITE_DEEPSEEK_API_KEY`, configure Gmail OAuth, then run a staged-image and inbox smoke test.

## Architecture

- `arc-toolbar/`: Tauri v2 + Vite vanilla JS floating desktop app. It has three layout modes (Nokia, Strip, Chat-first), a custom title bar, admin settings overlay, and a DeepSeek function-calling chat loop backed by Demo Bench MCP tools.
- `demo-bench/`: A standalone PySide6 desktop shell for client-facing Arcillis demos. A landing dialog selects a demo before its plugin supplies dockable document intake, source browsing, viewing, and batch-status widgets for Demo 2.

## File Map

- `arc-toolbar/index.html`: Vite entry point — root HTML shell with layout containers and Tabler Icons CDN.
- `arc-toolbar/src/main.js`: Toolbar state and layout engine, MCP/DeepSeek chat loop, structured display response parsing, display persistence, window sizing, admin settings, and Tauri window controls.
- `arc-toolbar/src/components.js`: DOM-only renderer for the number, text, table, status, progress, button, and divider display primitives.
- `arc-toolbar/src-tauri/capabilities/default.json`: Tauri v2 permissions for drag, minimize, close, resizing, and always-on-top operations.
- `arc-toolbar/src/style.css`: Dark theme with CSS custom properties, three layout modes, custom titlebar, and admin overlay styles.
- `arc-toolbar/src-tauri/src/main.rs`: Minimal Tauri binary entry point delegating to lib.
- `arc-toolbar/src-tauri/src/lib.rs`: Tauri v2 builder with generate_context!().
- `arc-toolbar/src-tauri/tauri.conf.json`: Window config — 280x480, decorations false, alwaysOnTop true, transparent true.
- `demo-bench/main.py`: Application shell, landing dialog launch, dock-layout reset, dark palette, and connection status indicator.
- `demo-bench/widgets/demo_selector_window.py`: Dark landing dialog and clickable Document Extractor demo card.
- `demo-bench/plugins/document_extractor.py`: Registers and lays out the Document Extractor intake, viewer, batch status, results table, and export docks.
- `demo-bench/mcp_server/`: FastAPI server on port 8098 with demo-scoped MCP-style tool discovery/calls, guarded read access, result summaries, CSV/Excel exports, live xlwings workbook tools, Gmail inbox scanning, and staged vision extraction. `start_mac.sh` connects to the PC Postgres instance through Tailscale.
- `demo-bench/widgets/chat_widget.py`: Floating assistant bubble that discovers Demo 2 tools, calls DeepSeek from worker threads, and emits local invoice-highlight requests.
- `demo-bench/widgets/results_table_widget.py`: Loads extraction records, grades, selectable rows, and field-level comparisons from Postgres.
- `demo-bench/widgets/export_widget.py`: Exports checked (or confirmed all) extraction records as CSV or formatted Excel.
- `demo-bench/widgets/`: Intake, lazy thumbnail browser, document viewer, batch-status, results-table, and export components.

## Last 10 Changes

- 2026-07-17: Fixed `sheets_snapshot` to detect and analyze only the Google Sheet's populated row and column range, while retaining the full grid dimensions for context.
- 2026-07-17: Added `sheets_snapshot` tool that returns a compressed structural summary of a Google Sheet — dimensions, frozen panes, merges, headers, column types/fill rates, sample rows, auto-detected issues, and optional formatting info. Registered in the Demo Bench MCP server under the `document_extractor` demo.
- 2026-07-17: Made every Demo Bench MCP database connection set `search_path` to `arcillis` explicitly, removing the fragile URL options fallback that broke psycopg2 URI parsing on macOS.
- 2026-07-17: Added gspread-backed Google Sheets MCP tools for writing formatted headers, live color-coded extraction rows, arbitrary cells, and reads. The macOS launcher now supplies the service-account credential path.
- 2026-07-17: Added Mac-runnable MCP startup and four live Excel tools: cell read/write, basic formatting, and color-coded extraction row output. The MCP database URL is now configurable so macOS connects to PC Postgres through Tailscale.
- 2026-07-16: Added ARC Toolbar's structured component display system. The Nokia screen now defaults to a persisted dashboard with seven DOM-rendered primitives, responsive rows, an in-place chat fallback, intent buttons, loading overlay, animated preset sizing, and runtime admin controls for display configuration.
- 2026-07-16: Wired ARC Toolbar chat and action buttons to DeepSeek function calling with the Demo Bench MCP server. Added schema-scoped Demo 2 DB access, Gmail inbox scanning, staged image/PDF extraction, and Tauri capability permissions.
- 2026-07-15: Enabled Tauri v2 Cargo features for macOS — `devtools` + `macos-private-api` in Cargo.toml, `macOSPrivateApi: true` in tauri.conf.json, for transparent windows and drag.
- 2026-07-15: Fixed ARC Toolbar window drag and close on macOS — added `startDragging()` on titlebar mousedown, try/catch on minimize/close, `-webkit-app-region` CSS fallback, and console logging.
- 2026-07-15: Added ARC Toolbar — a Tauri (v2) + Vite vanilla JS floating desktop app with three layout modes (Nokia, Strip, Chat-first), mock data, custom title bar, and an admin overlay. Visual prototype only; no backend connections.
- 2026-07-15: Added a workflow navigation bar to the Document Extractor demo. It defaults to Browse, switches tab-specific docks while retaining document and batch context, and makes the floating chat panel a top-level tool window above dock widgets.

## Known Issues

- The local OpenCode vision proxy on port 4096 must be running and compatible with the configured model before `run_extraction` can process staged files.
- `scan_inbox` needs a valid `GMAIL_CREDENTIALS_PATH`; its first run opens a local OAuth consent flow and stores `gmail-token.json` beside those credentials.
- The Mac bridge timed out during this task, so `start_mac.sh` and real Excel automation still need a manual macOS verification with an open workbook.
