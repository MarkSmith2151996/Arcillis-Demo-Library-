"""Postgres access for the Demo Bench desktop application."""

from __future__ import annotations

import psycopg2


DB_URL = "postgresql://autocore_writer:autocore_pipeline_2026@100.95.20.98:5432/hive"


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
