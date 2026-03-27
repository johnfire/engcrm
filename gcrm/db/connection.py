import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from gcrm.config import DATABASE_URL


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
