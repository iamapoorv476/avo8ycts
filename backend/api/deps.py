"""FastAPI dependency: a request-scoped SQLite connection.

Mirrors the project's single-DB-file simplicity decision (see
ingestion/run_ingestion_pipeline.py) -- one connection per request, opened
and closed around the request rather than shared globally, since SQLite
connections aren't meant to be shared across threads/requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import get_connection  


def get_db():
    
    conn = get_connection(check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()