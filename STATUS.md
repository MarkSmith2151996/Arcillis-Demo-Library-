# Arcillis Demo Library Status

## Project

- Custodian project: `arcillis-demo-library`
- Stack: Python + React + Claude API + Google Sheets API + ChromaDB
- Current state: Repo bootstrapped; no demos built yet.
- Next: Demo 2 (PDF extractor) is the first build target.

## Last 10 Changes

- 2026-07-13: Completed direct agent-vision extraction for all 125 mychen76 test receipts under `mychen76-test-run`; schema-agnostic grading averaged 79.10%, with a 0.00% to 100.00% range and no unreadable-image error records.
- 2026-07-13: Downloaded and materialized 295 mychen76 invoice/receipt records for Demo 2 stress testing (100 train, 125 test, 70 valid), then loaded them idempotently into `arcillis.demo2_invoice` under the `mychen76` dataset source. The 259 MB local dataset is gitignored; 174 records use the Donut-compatible `header`/`items`/`summary` form, while 120 receipt records are flat and one valid record is wrapped under `None`.
- 2026-07-12: Downloaded and materialized the Donut invoice evaluation dataset locally; documented its ground-truth schema and Git-ignore policy.
- 2026-07-12: Bootstrapped the repository with demo and shared-component placeholders.

## Known Issues

- None.
