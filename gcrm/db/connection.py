import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import date, datetime

from gcrm.config import DATABASE_URL


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
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
