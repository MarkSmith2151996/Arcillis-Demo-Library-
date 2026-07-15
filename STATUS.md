# Arcillis Demo Library Status

## Project

- Custodian project: `arcillis-demo-library`
- Stack: Python + PySide6 + FastAPI + DeepSeek API + Postgres + Google Sheets API + ChromaDB + Tauri v2 (arc-toolbar)
- Current state: Demo 2 extraction pipeline and the Demo Bench MCP/chat controls are implemented; the local vision proxy must be started before a live smoke test. ARC Toolbar is a visual prototype with no backend connections.
- Next: Start the OpenCode proxy and the Demo Bench MCP server, set `DEEPSEEK_API_KEY`, then run the three-image Demo 2 smoke test.

## Architecture

- `arc-toolbar/`: Tauri v2 + Vite vanilla JS floating desktop app. Visual prototype with three layout modes (Nokia, Strip, Chat-first), custom title bar, mock state, and admin settings overlay.
- `demo-bench/`: A standalone PySide6 desktop shell for client-facing Arcillis demos. A landing dialog selects a demo before its plugin supplies dockable document intake, source browsing, viewing, and batch-status widgets for Demo 2.

## File Map

- `arc-toolbar/index.html`: Vite entry point — root HTML shell with layout containers and Tabler Icons CDN.
- `arc-toolbar/src/main.js`: Layout rendering engine, mock state, admin overlay, keyboard shortcuts, and window controls via Tauri API.
- `arc-toolbar/src/style.css`: Dark theme with CSS custom properties, three layout modes, custom titlebar, and admin overlay styles.
- `arc-toolbar/src-tauri/src/main.rs`: Minimal Tauri binary entry point delegating to lib.
- `arc-toolbar/src-tauri/src/lib.rs`: Tauri v2 builder with generate_context!().
- `arc-toolbar/src-tauri/tauri.conf.json`: Window config — 280x480, decorations false, alwaysOnTop true, transparent true.
- `demo-bench/main.py`: Application shell, landing dialog launch, dock-layout reset, dark palette, and connection status indicator.
- `demo-bench/widgets/demo_selector_window.py`: Dark landing dialog and clickable Document Extractor demo card.
- `demo-bench/plugins/document_extractor.py`: Registers and lays out the Document Extractor intake, viewer, batch status, results table, and export docks.
- `demo-bench/mcp_server/`: FastAPI server on port 8098 with demo-scoped MCP-style tool discovery/calls, guarded read access, result summaries, and local CSV/Excel exports.
- `demo-bench/widgets/chat_widget.py`: Floating assistant bubble that discovers Demo 2 tools, calls DeepSeek from worker threads, and emits local invoice-highlight requests.
- `demo-bench/widgets/results_table_widget.py`: Loads extraction records, grades, selectable rows, and field-level comparisons from Postgres.
- `demo-bench/widgets/export_widget.py`: Exports checked (or confirmed all) extraction records as CSV or formatted Excel.
- `demo-bench/widgets/`: Intake, lazy thumbnail browser, document viewer, batch-status, results-table, and export components.

## Last 10 Changes

- 2026-07-15: Added ARC Toolbar — a Tauri (v2) + Vite vanilla JS floating desktop app with three layout modes (Nokia, Strip, Chat-first), mock data, custom title bar, and an admin overlay. Visual prototype only; no backend connections.
- 2026-07-15: Added a workflow navigation bar to the Document Extractor demo. It defaults to Browse, switches tab-specific docks while retaining document and batch context, and makes the floating chat panel a top-level tool window above dock widgets.
- 2026-07-15: Added a Demo Bench FastAPI MCP server with guarded Demo 2 query, detail, summary, export, and reprocess tools, plus a threaded floating DeepSeek chat widget that can highlight result-table invoices.
- 2026-07-15: Added Demo Bench Results Table and Export docks. Results display extraction grades, selectable records, source-image navigation, and field-level ground-truth comparisons; checked records export to CSV or Excel.
- 2026-07-14: Switched Demo Bench thumbnail and document loading from the PC HTTP file server to locally synced Mac paths, including `mac-local://` uploads, so image viewing works offline once datasets are present.
- 2026-07-14: Made Demo Bench source-path conversion handle absolute and dataset-relative database paths, URL-encode filenames, log every thumbnail/document request and HTTP result, show source filenames on failures, use smaller five-column thumbnail cells, make File Browser the central workspace, narrow Intake, and guard dock-grid cleanup from null widgets.
- 2026-07-13: Updated Demo Bench to fetch WSL-hosted source images asynchronously through the PC file server, mark Mac-only intake uploads as intentionally remote-unavailable, and open with a dark Document Extractor landing dialog instead of a selector sidebar.
- 2026-07-13: Added the dockable PySide6 Demo Bench shell for the Document Extractor demo. It includes a plugin registry, Postgres connection indicator, dark palette, local PDF/image intake, lazy filtered database thumbnail browser, zoomable viewer, and batch-status placeholder.
- 2026-07-13: Added Demo 2's standalone output MCP server. Its Excel, CSV, and Google Sheets tools fetch a run or accept raw extraction JSON, emit an identical flattened table structure, format local workbooks, and clearly skip Sheets when no service account is configured.
- 2026-07-13: Completed direct agent-vision extraction for all 125 mychen76 test receipts under `mychen76-test-run`; schema-agnostic grading averaged 79.10%, with a 0.00% to 100.00% range and no unreadable-image error records.

## Known Issues

- The local OpenCode vision proxy on port 4096 was unavailable during AC-054 implementation, so live model extraction remains unverified until the proxy is started.
