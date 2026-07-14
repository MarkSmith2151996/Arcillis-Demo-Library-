"""Postgres access for the Demo Bench desktop application."""

from __future__ import annotations

import psycopg2
from urllib.parse import quote


DB_URL = "postgresql://autocore_writer:autocore_pipeline_2026@100.95.20.98:5432/hive"
FILE_SERVER_URL = "http://100.95.20.98:9999"
REPOSITORY_ROOT = "/home/dev/projects/Arcillis-Demo-Library/"
DATASET_ROOT = "demo-2-pdf-extractor/"


def image_path_to_url(image_path: str) -> str:
    """Map stored source paths to paths exposed by the repository file server."""
    path = image_path.replace("\\", "/")
    if path.startswith(REPOSITORY_ROOT):
        relative = path.removeprefix(REPOSITORY_ROOT)
    else:
        relative = path.lstrip("/")
        if relative.startswith(("datasets/", "donut-invoices/", "mychen76/")):
            relative = f"{DATASET_ROOT}{relative}"
    return f"{FILE_SERVER_URL}/{quote(relative, safe='/')}"


def get_connection():
    """Open a short-lived connection to the shared Arcillis database."""
    return psycopg2.connect(DB_URL, connect_timeout=10)


def is_available() -> bool:
    """Return whether the remote database can be reached."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        return True
    except psycopg2.Error:
        return False
