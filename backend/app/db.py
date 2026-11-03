"""Minimal Postgres connection. Only used for the health check for now."""

import os
import psycopg

def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER") or "rohingya",
        password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB") or "rohingya",
        connect_timeout=3,
    )


def ping() -> bool:
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False
