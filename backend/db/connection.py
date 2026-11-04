"""SQLite connection helper.

Single responsibility: know where the database file lives, how to open a
connection to it (with foreign keys and row access configured), and how to
(re)create the schema from schema.sql. Nothing else lives here.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "wind_forecast.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema() -> None:
    
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