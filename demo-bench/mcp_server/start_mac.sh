#!/bin/bash
# Start the MCP server on macOS and reach Postgres on the PC over Tailscale.
set -e

cd "$(dirname "$0")"
export DATABASE_URL="postgresql://autocore_writer:autocore_pipeline_2026@100.95.20.98:5432/hive?options=-csearch_path%3Darcillis"
pip install -r requirements.txt
exec uvicorn server:app --host 0.0.0.0 --port 8098
