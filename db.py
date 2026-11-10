"""Database initialization and connection management."""

import os
import hashlib
from pathlib import Path
from typing import Optional

import config

SQLITE_SCHEMA_PATH = config.BASE_DIR / "schema.sqlite.sql"
POSTGRES_SCHEMA_PATH = config.BASE_DIR / "schema.postgres.sql"

_DATABASE_URL = os.getenv("DATABASE_URL")
_USING_POSTGRES = bool(_DATABASE_URL)

if _USING_POSTGRES:
    import psycopg2
    import psycopg2.extras

_POSTGRES_TEST_SCHEMAS: set[str] = set()


def _convert_placeholders(statement: str) -> str:
    """Convert qmark parameters outside SQL quoted strings and comments."""
    converted = []
    quote = None
    line_comment = False
    block_comment = False
    index = 0

    while index < len(statement):
        char = statement[index]
        following = statement[index + 1] if index + 1 < len(statement) else ""

        if line_comment:
            converted.append(char)
            line_comment = char != "\n"
        elif block_comment:
            converted.append(char)
            if char == "*" and following == "/":
                converted.append(following)
                index += 1
                block_comment = False
        elif quote:
            converted.append(char)
            if char == quote:
                if following == quote:
                    converted.append(following)
                    index += 1
                else:
                    quote = None
            elif char == "\\" and quote == "'":
                if following:
                    converted.append(following)
                    index += 1
        elif char == "-" and following == "-":
            converted.extend((char, following))
            index += 1
            line_comment = True
        elif char == "/" and following == "*":
            converted.extend((char, following))
            index += 1
            block_comment = True
        elif char in {"'", '"'}:
            quote = char
            converted.append(char)
        else:
            converted.append("%s" if char == "?" else char)
        index += 1

    return "".join(converted)


class DatabaseCursor:
    """Cursor adapter that returns mapping rows consistently."""

    def __init__(self, cursor, postgres: bool):
        self._cursor = cursor
        self._postgres = postgres

    def _as_dict(self, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return dict(row)
        return {column[0]: value for column, value in zip(self._cursor.description, row)}

    def fetchone(self):
        return self._as_dict(self._cursor.fetchone())

    def fetchall(self):
        return [self._as_dict(row) for row in self._cursor.fetchall()]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid if not self._postgres else None


class DatabaseConnection:
    """Connection adapter for the SQL shared by SQLite and PostgreSQL."""

    def __init__(self, connection, postgres: bool):
        self._connection = connection
        self._postgres = postgres

    def execute(self, statement: str, parameters=()):
        if self._postgres:
            cursor = self._connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(_convert_placeholders(statement), parameters)
        else:
            cursor = self._connection.execute(statement, parameters)
        return DatabaseCursor(cursor, self._postgres)

    def executescript(self, script: str) -> None:
        if not self._postgres:
            self._connection.executescript(script)
            return
        for statement in filter(None, (part.strip() for part in script.split(";"))):
            self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


def get_connection(db_path: Optional[Path] = None) -> DatabaseConnection:
    """Return a backend-neutral connection; non-default paths isolate test data."""
    if _USING_POSTGRES:
        path = Path(db_path or config.DB_PATH).resolve()
        production_path = (config.BASE_DIR / "sabilab.db").resolve()
        if path == production_path:
            raw_connection = psycopg2.connect(_DATABASE_URL)
        else:
            schema = "sabi_test_" + hashlib.sha256(str(path).encode()).hexdigest()[:20]
            if schema not in _POSTGRES_TEST_SCHEMAS:
                setup_connection = psycopg2.connect(_DATABASE_URL)
                try:
                    setup_connection.autocommit = True
                    with setup_connection.cursor() as cursor:
                        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                finally:
                    setup_connection.close()
                _POSTGRES_TEST_SCHEMAS.add(schema)
            raw_connection = psycopg2.connect(
                _DATABASE_URL,
                options=f"-c search_path={schema}",
            )
        return DatabaseConnection(raw_connection, postgres=True)

    import sqlite3

    path = db_path or config.DB_PATH
    raw_connection = sqlite3.connect(str(path))
    return DatabaseConnection(raw_connection, postgres=False)


def insert_id(connection: DatabaseConnection, statement: str, parameters=()) -> int:
    """Insert a row and return its generated integer ID on either backend."""
    if _USING_POSTGRES:
        insert = statement.rstrip().rstrip(";")
        row = connection.execute(f"{insert} RETURNING id", parameters).fetchone()
        return row["id"]
    return connection.execute(statement, parameters).lastrowid


def get_table_names(db_path: Optional[Path] = None) -> set[str]:
    """Return table names in the active database schema."""
    connection = get_connection(db_path)
    try:
        if _USING_POSTGRES:
            rows = connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT name AS table_name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        return {row["table_name"] for row in rows}
    finally:
        connection.close()


def _has_column(connection: DatabaseConnection, table: str, column: str) -> bool:
    if _USING_POSTGRES:
        row = connection.execute(
            "SELECT 1 AS present FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? AND column_name = ?",
            (table, column),
        ).fetchone()
        return row is not None

    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in columns)


def init_db(db_path: Optional[Path] = None) -> None:
    """Create all required tables idempotently and apply additive migrations."""
    connection = get_connection(db_path)
    schema_path = POSTGRES_SCHEMA_PATH if _USING_POSTGRES else SQLITE_SCHEMA_PATH
    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        if not _has_column(connection, "sessions", "attempt_number"):
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1"
            )
        connection.commit()
    finally:
        connection.close()
