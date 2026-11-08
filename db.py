"""Database initialization and connection management using SQLite."""

import sqlite3
from typing import Optional
from pathlib import Path
import config

SCHEMA_PATH = config.BASE_DIR / "schema.sql"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return an active SQLite database connection with row factory configured."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Create all required tables from Build Spec Section 3 if they do not exist."""
    conn = get_connection(db_path)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        # Migration: add attempt_number column if missing (safe on existing DBs)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "attempt_number" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    finally:
        conn.close()
