# Demo 2: PDF Extractor

Invoice image to structured JSON with ground-truth grading. The extractor sends images to the
local OpenCode OpenAI-compatible vision proxy, then stores its result and field-level accuracy in
Postgres.

## Setup

```bash
cp .env.example .env
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python demo-2-pdf-extractor/load_ground_truth.py
.venv/bin/python demo-2-pdf-extractor/run_extraction.py --run-id smoke-test --limit 3
```

The OpenCode proxy must be available at `http://localhost:4096/v1`. The runner makes a bounded
text-only verification request before processing images and exits with a clear error when the proxy
is unavailable.

## Dataset Schema

The normal form is nested `header`, `items`, and `summary` objects. Ten source records use a flat
form, which the loader preserves and the grader canonicalizes before comparison.
