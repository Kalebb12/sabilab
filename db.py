"""Database initialization and connection management."""

import os
from typing import Optional
from pathlib import Path
import config

SCHEMA_PATH = config.BASE_DIR / "schema.sql"

_DATABASE_URL = os.getenv("DATABASE_URL")
_USING_POSTGRES = bool(_DATABASE_URL)

if _USING_POSTGRES:
    import psycopg2
    import psycopg2.extras

def get_connection(db_path: Optional[Path] = None):
    """Return an active DB connection (Postgres or SQLite)."""
    if _USING_POSTGRES:
        conn = psycopg2.connect(_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    else:
        import sqlite3
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
        if _USING_POSTGRES:
            # Split on semicolons, skip empty
            for stmt in filter(None, (s.strip() for s in schema_sql.split(";"))):
                if stmt:
                    try:
                        conn.cursor().execute(stmt)
                    except Exception as e:
                        if 'already exists' in str(e) or 'duplicate column' in str(e):
                            pass
                        else:
                            raise
            # Migration: add attempt_number column if missing
            cur = conn.cursor()
            cur.execute("""
                SELECT column_name FROM information_schema.columns WHERE table_name='sessions' AND column_name='attempt_number'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE sessions ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        else:
            conn.executescript(schema_sql)
            # Migration: add attempt_number column if missing (safe on existing DBs)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
            if "attempt_number" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1")
            conn.commit()
    finally:
        conn.close()
