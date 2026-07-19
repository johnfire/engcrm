"""Audit context resolution and non-blocking audit persistence tests."""
from unittest.mock import MagicMock, patch

from gcrm.audit_context import audit_scope, current_audit_context
from gcrm.mcp.server import mcp_mutation
from gcrm.tools.db_audit import log_audit


def test_log_audit_uses_the_active_actor_and_correlation_id():
    connection = MagicMock()
    with patch("gcrm.tools.db_audit.db") as mock_db:
        mock_db.return_value.__enter__.return_value = connection
        with audit_scope("agent:scout_agent", "ai", "run:42"):
            log_audit(None, None, "contact.scored", "contact:7", "cold")

    params = connection.cursor.return_value.execute.call_args.args[1]
    assert params == ("agent:scout_agent", "ai", "contact.scored", "contact:7", "cold", "run:42")


def test_log_audit_does_not_block_the_action_when_storage_fails():
    with patch("gcrm.tools.db_audit.db", side_effect=RuntimeError("database unavailable")):
        log_audit("mcp-client", "mcp", "contact.manual_drop", "contact:7", "dropped")


def test_mcp_mutation_sets_a_recordable_client_actor():
    @mcp_mutation
    def active_context():
        return current_audit_context()

    context = active_context()

    assert context.actor == "mcp-client"
    assert context.actor_type == "mcp"
    assert context.correlation_id.startswith("mcp:")
