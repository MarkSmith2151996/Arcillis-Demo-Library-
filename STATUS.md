# Arcillis Demo Library Status

## Project

- Custodian project: `arcillis-demo-library`
- Stack: Python + React + Claude API + Google Sheets API + ChromaDB
- Current state: Demo 2 extraction pipeline is implemented; the local vision proxy must be started before a live smoke test.
- Next: Start the OpenCode proxy and run the three-image Demo 2 smoke test.

## Architecture

- `demo-bench/`: A standalone PySide6 desktop shell for client-facing Arcillis demos. The first plugin supplies dockable document intake, source browsing, viewing, and batch-status widgets for Demo 2.

## File Map

- `demo-bench/main.py`: Application shell, demo selector, dock-layout reset, dark palette, and connection status indicator.
- `demo-bench/plugins/document_extractor.py`: Registers and lays out the four Document Extractor docks.
- `demo-bench/widgets/`: Intake, lazy thumbnail browser, document viewer, and batch-status components.

## Last 10 Changes

- 2026-07-13: Added the dockable PySide6 Demo Bench shell for the Document Extractor demo. It includes a plugin registry, Postgres connection indicator, dark palette, local PDF/image intake, lazy filtered database thumbnail browser, zoomable viewer, and batch-status placeholder.
- 2026-07-13: Added Demo 2's standalone output MCP server. Its Excel, CSV, and Google Sheets tools fetch a run or accept raw extraction JSON, emit an identical flattened table structure, format local workbooks, and clearly skip Sheets when no service account is configured.
- 2026-07-13: Completed direct agent-vision extraction for all 125 mychen76 test receipts under `mychen76-test-run`; schema-agnostic grading averaged 79.10%, with a 0.00% to 100.00% range and no unreadable-image error records.
- 2026-07-13: Downloaded and materialized 295 mychen76 invoice/receipt records for Demo 2 stress testing (100 train, 125 test, 70 valid), then loaded them idempotently into `arcillis.demo2_invoice` under the `mychen76` dataset source. The 259 MB local dataset is gitignored; 174 records use the Donut-compatible `header`/`items`/`summary` form, while 120 receipt records are flat and one valid record is wrapped under `None`.
- 2026-07-13: Added Demo 2's idempotent Donut ground-truth loader, OpenCode vision extractor, field-level auto-grader, and Postgres batch runner. The 501-record dataset has nested and flat variants; grading canonicalizes both.
- 2026-07-12: Downloaded and materialized the Donut invoice evaluation dataset locally; documented its ground-truth schema and Git-ignore policy.
- 2026-07-12: Bootstrapped the repository with demo and shared-component placeholders.

## Known Issues

- The local OpenCode vision proxy on port 4096 was unavailable during AC-054 implementation, so live model extraction remains unverified until the proxy is started.
