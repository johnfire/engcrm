"""
Run all pending migrations against the shared gcrm PostgreSQL database.
Usage: uv run python scripts/migrate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

from gcrm.db.connection import db

MIGRATIONS_DIR = Path(__file__).parent.parent / "gcrm" / "db" / "migrations"


def ensure_migration_tracking_table(cursor) -> None:
    """Create the runner's bookkeeping table before the first migration exists."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) NOT NULL UNIQUE,
            applied_at TIMESTAMPTZ DEFAULT NOW(),
            checksum VARCHAR(64),
            execution_time_ms INTEGER,
            rolled_back_at TIMESTAMPTZ,
            rollback_reason TEXT
        )
        """
    )


def run():
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print("No migration files found.")
        return

    with db() as conn:
        cur = conn.cursor()
        ensure_migration_tracking_table(cur)
        cur.execute("SELECT migration_name FROM schema_migrations")
        applied = {r["migration_name"] for r in cur.fetchall()}

        ran = 0
        for f in sql_files:
            if f.name in applied:
                print(f"Skipping {f.name} (already applied)")
                continue
            print(f"Running {f.name}...")
            cur.execute(f.read_text())
            cur.execute(
                "INSERT INTO schema_migrations (migration_name) VALUES (%s) ON CONFLICT DO NOTHING",
                (f.name,),
            )
            ran += 1
        print(f"Done. {ran} migration(s) applied.")


if __name__ == "__main__":
    run()
