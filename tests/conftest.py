"""
Set test environment variables before application imports. Unit tests use a
dummy URL; CI integration and e2e tests opt into a real Postgres service with
TEST_DATABASE_URL.
"""
import os
import sys
from pathlib import Path
from subprocess import run

if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("MAIL_USERNAME", "test@test.com")
os.environ.setdefault("MAIL_PASSWORD", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production")
os.environ.setdefault("EMAIL_ENABLED", "false")

import pytest


@pytest.fixture(scope="session")
def migrated_database():
    """Apply all migrations to CI's disposable PostgreSQL service once."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("real database tests require TEST_DATABASE_URL")

    repository_root = Path(__file__).parent.parent
    run([sys.executable, "scripts/migrate.py"], cwd=repository_root, check=True)
    return database_url


@pytest.fixture
def clean_database(migrated_database):
    """Isolate a real-database test without removing its migration history."""
    import psycopg2

    connection = psycopg2.connect(migrated_database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DO $$
                DECLARE truncate_statement TEXT;
                BEGIN
                    SELECT 'TRUNCATE TABLE ' || string_agg(quote_ident(tablename), ', ')
                        || ' RESTART IDENTITY CASCADE'
                    INTO truncate_statement
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename NOT IN (
                          'schema_migrations', 'workspaces', 'lookup_values', 'ignored_chains'
                      );
                    EXECUTE truncate_statement;
                END $$;
                """
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """Start each test with a clean auth rate limiter so the process-global
    counter doesn't couple otherwise-independent tests."""
    from gcrm.api.rate_limit import _auth_limiter
    _auth_limiter.reset()
    yield
