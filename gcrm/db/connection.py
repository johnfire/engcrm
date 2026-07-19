from contextlib import contextmanager
from datetime import date, datetime

import psycopg2
import psycopg2.extras

from gcrm.config import DATABASE_URL
from gcrm.workspace_context import get_workspace_id


def serialize_row(row: dict) -> dict:
    """Convert datetime/date objects to ISO strings so rows are JSON-safe."""
    return {
        key: value.isoformat() if isinstance(value, (datetime, date)) else value
        for key, value in row.items()
    }


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@contextmanager
def db():
    """Context manager for a single connection with auto-commit on success."""
    conn = get_connection()
    try:
        workspace_id = get_workspace_id()
        if workspace_id is not None:
            conn.cursor().execute("SELECT set_config('app.workspace_id', %s, TRUE)", (str(workspace_id),))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
