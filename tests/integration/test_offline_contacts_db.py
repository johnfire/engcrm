"""Monthly manual counts persist without creating CRM records and obey workspace isolation."""
import uuid
from contextlib import contextmanager
from datetime import date

import pytest

from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.tools.db_offline_contacts import get_offline_totals, save_offline_total
from gcrm.workspace_context import get_workspace_id, set_workspace_id

pytestmark = pytest.mark.integration


@contextmanager
def workspace_scope(workspace):
    previous = get_workspace_id()
    set_workspace_id(workspace)
    try:
        yield
    finally:
        set_workspace_id(previous)


def test_monthly_statistics_replace_only_the_manual_count_and_sum_from_start(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
    with workspace_scope(workspace), audit_scope("offline@example.test", "user", "offline-test"):
        save_offline_total(date(2026, 10, 1), 35)
        save_offline_total(date(2026, 10, 1), 35)  # Retrying a save cannot add a second batch.
        save_offline_total(date(2026, 11, 1), 36)
        assert get_offline_totals(date(2026, 11, 6)) == {"2026-10-01": 35, "2026-11-01": 36}
        save_offline_total(date(2026, 11, 1), 37)
        assert sum(get_offline_totals(date(2026, 11, 6)).values()) == 72
        assert get_offline_totals(date(2026, 10, 31)) == {"2026-10-01": 35}
    with db() as connection:
        cursor = connection.cursor()
        for table in ("people", "contacts", "interactions", "people_interactions"):
            cursor.execute(f"SELECT COUNT(*) AS n FROM {table}")
            assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT actor,correlation_id,outcome FROM audit_log WHERE action='offline_contacts.updated'")
        entries = cursor.fetchall()
        assert len(entries) == 4
        assert all(entry["actor"] == "offline@example.test" and entry["correlation_id"] == "offline-test" for entry in entries)


def test_manual_counts_are_hidden_from_other_workspaces(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (slug,name) VALUES (%s,'Offline tests') RETURNING id", (uuid.uuid4().hex,))
        first = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        other = cursor.fetchone()["id"]
    with workspace_scope(first):
        save_offline_total(date(2026, 11, 1), 35)
    with workspace_scope(other):
        assert get_offline_totals(date(2026, 11, 6)) == {}
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM offline_contact_totals WHERE workspace_id=%s", (first,))
            assert cursor.fetchall() == []
        with pytest.raises(Exception, match="row-level security"):
            with db() as connection:
                connection.cursor().execute("INSERT INTO offline_contact_totals VALUES (%s,'2026-10-01',99)", (first,))
