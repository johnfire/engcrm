"""
Run all pending migrations against the shared artcrm PostgreSQL database.
Usage: uv run python scripts/migrate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from gcrm.db.connection import db

MIGRATIONS_DIR = Path(__file__).parent.parent / "src" / "db" / "migrations"


def run():
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print("No migration files found.")
        return

    with db() as conn:
        cur = conn.cursor()
        for f in sql_files:
            print(f"Running {f.name}...")
            cur.execute(f.read_text())
        print(f"Done. {len(sql_files)} migration(s) applied.")


if __name__ == "__main__":
    run()
