"""SQLite connection helper.

Single responsibility: know where the database file lives, how to open a
connection to it (with foreign keys and row access configured), and how to
(re)create the schema from schema.sql. Nothing else lives here.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "wind_forecast.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Open a connection to the project database.

    Row access via column name (sqlite3.Row) rather than positional index,
    so downstream code reads as row["generation"] instead of row[2] — fails
    loudly on a typo'd column name instead of silently reading the wrong field.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema() -> None:
    """(Re)create all tables from schema.sql. Destructive: drops existing tables first.

    This is intentional for this project's scope — a one-off ingestion pipeline
    over a fixed historical window, not a live system with data to preserve
    across schema changes. Re-running ingestion is the expected way to pick up
    a schema change.
    """
    conn = get_connection()
    try:
        with open(SCHEMA_PATH) as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
    print(f"Schema initialized at {DB_PATH}")