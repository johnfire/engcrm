"""A real background thread must retain the requesting workspace."""
from threading import Event
from unittest.mock import MagicMock

from gcrm.audit_context import audit_scope, current_audit_context
from gcrm.tools.db_company_web import start_web_job
from gcrm.workspace_context import get_workspace_id, set_workspace_id


def test_company_lookup_thread_keeps_the_request_workspace(monkeypatch):
    completed = Event()
    observed_workspaces = []

    def record_workspace(limit):
        observed_workspaces.append((get_workspace_id(), limit))
        completed.set()

    monkeypatch.setattr("gcrm.tools.db_company_web.is_job_running", lambda: False)
    monkeypatch.setattr("gcrm.tools.db_company_web._job", record_workspace)
    set_workspace_id(57)
    try:
        assert start_web_job(5)
        assert completed.wait(2)
        assert observed_workspaces == [(57, 5)]
    finally:
        set_workspace_id(None)


def test_lookup_worker_records_ai_identity_with_the_request_correlation(monkeypatch):
    from gcrm.tools.db_company_web import _job

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.fetchone.return_value = {"got": True}
    monkeypatch.setattr("gcrm.tools.db_company_web.db", lambda: connection)
    observed = []
    monkeypatch.setattr("gcrm.tools.db_company_web.resolve_company_websites", lambda **kwargs: observed.append(current_audit_context()))
    with audit_scope("owner@example.test", "user", "request-57"):
        _job(5)
        assert current_audit_context().actor == "owner@example.test"
    assert len(observed) == 1
    assert observed[0].actor == "agent:company_web_lookup"
    assert observed[0].actor_type == "ai"
    assert observed[0].correlation_id == "request-57"
