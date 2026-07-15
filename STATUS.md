# Arcillis Demo Library Status

## Project

- Custodian project: `arcillis-demo-library`
- Stack: Python + PySide6 + FastAPI + DeepSeek API + Postgres + Google Sheets API + ChromaDB
- Current state: Demo 2 extraction pipeline and the Demo Bench MCP/chat controls are implemented; the local vision proxy must be started before a live smoke test.
- Next: Start the OpenCode proxy and the Demo Bench MCP server, set `DEEPSEEK_API_KEY`, then run the three-image Demo 2 smoke test.

## Architecture

- `demo-bench/`: A standalone PySide6 desktop shell for client-facing Arcillis demos. A landing dialog selects a demo before its plugin supplies dockable document intake, source browsing, viewing, and batch-status widgets for Demo 2.

## File Map

- `demo-bench/main.py`: Application shell, landing dialog launch, dock-layout reset, dark palette, and connection status indicator.
- `demo-bench/widgets/demo_selector_window.py`: Dark landing dialog and clickable Document Extractor demo card.
- `demo-bench/plugins/document_extractor.py`: Registers and lays out the Document Extractor intake, viewer, batch status, results table, and export docks.
- `demo-bench/mcp_server/`: FastAPI server on port 8098 with demo-scoped MCP-style tool discovery/calls, guarded read access, result summaries, and local CSV/Excel exports.
- `demo-bench/widgets/chat_widget.py`: Floating assistant bubble that discovers Demo 2 tools, calls DeepSeek from worker threads, and emits local invoice-highlight requests.
- `demo-bench/widgets/results_table_widget.py`: Loads extraction records, grades, selectable rows, and field-level comparisons from Postgres.
- `demo-bench/widgets/export_widget.py`: Exports checked (or confirmed all) extraction records as CSV or formatted Excel.
- `demo-bench/widgets/`: Intake, lazy thumbnail browser, document viewer, batch-status, results-table, and export components.

## Last 10 Changes

- 2026-07-15: Added a Demo Bench FastAPI MCP server with guarded Demo 2 query, detail, summary, export, and reprocess tools, plus a threaded floating DeepSeek chat widget that can highlight result-table invoices.
- 2026-07-15: Added Demo Bench Results Table and Export docks. Results display extraction grades, selectable records, source-image navigation, and field-level ground-truth comparisons; checked records export to CSV or Excel.
- 2026-07-14: Switched Demo Bench thumbnail and document loading from the PC HTTP file server to locally synced Mac paths, including `mac-local://` uploads, so image viewing works offline once datasets are present.
- 2026-07-14: Made Demo Bench source-path conversion handle absolute and dataset-relative database paths, URL-encode filenames, log every thumbnail/document request and HTTP result, show source filenames on failures, use smaller five-column thumbnail cells, make File Browser the central workspace, narrow Intake, and guard dock-grid cleanup from null widgets.
- 2026-07-13: Updated Demo Bench to fetch WSL-hosted source images asynchronously through the PC file server, mark Mac-only intake uploads as intentionally remote-unavailable, and open with a dark Document Extractor landing dialog instead of a selector sidebar.
- 2026-07-13: Added the dockable PySide6 Demo Bench shell for the Document Extractor demo. It includes a plugin registry, Postgres connection indicator, dark palette, local PDF/image intake, lazy filtered database thumbnail browser, zoomable viewer, and batch-status placeholder.
- 2026-07-13: Added Demo 2's standalone output MCP server. Its Excel, CSV, and Google Sheets tools fetch a run or accept raw extraction JSON, emit an identical flattened table structure, format local workbooks, and clearly skip Sheets when no service account is configured.
- 2026-07-13: Completed direct agent-vision extraction for all 125 mychen76 test receipts under `mychen76-test-run`; schema-agnostic grading averaged 79.10%, with a 0.00% to 100.00% range and no unreadable-image error records.
- 2026-07-13: Downloaded and materialized 295 mychen76 invoice/receipt records for Demo 2 stress testing (100 train, 125 test, 70 valid), then loaded them idempotently into `arcillis.demo2_invoice` under the `mychen76` dataset source. The 259 MB local dataset is gitignored; 174 records use the Donut-compatible `header`/`items`/`summary` form, while 120 receipt records are flat and one valid record is wrapped under `None`.
- 2026-07-13: Added Demo 2's idempotent Donut ground-truth loader, OpenCode vision extractor, field-level auto-grader, and Postgres batch runner. The 501-record dataset has nested and flat variants; grading canonicalizes both.

## Known Issues

- The local OpenCode vision proxy on port 4096 was unavailable during AC-054 implementation, so live model extraction remains unverified until the proxy is started.
