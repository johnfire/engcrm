"""Interactive workspace queries must avoid PostgreSQL's expensive JIT preparation."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_contact_feed_query import contact_feed_sql
from gcrm.workspace_context import require_workspace_scope, set_workspace_id

pytestmark = pytest.mark.integration


@pytest.fixture
def request_workspace(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace_id = cursor.fetchone()["id"]
        cursor.execute("SHOW jit")
        operator_setting = cursor.fetchone()["jit"]
    set_workspace_id(workspace_id)
    require_workspace_scope()
    try:
        yield workspace_id, operator_setting
    finally:
        set_workspace_id(None)
        require_workspace_scope(False)


def test_request_queries_keep_workspace_role_without_query_compilation(request_workspace):
    workspace_id, _ = request_workspace
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT current_user AS role, current_setting('app.workspace_id') AS workspace, "
                       "current_setting('jit') AS compilation")
        assert dict(cursor.fetchone()) == {"role": "engcrm_workspace", "workspace": str(workspace_id),
                                          "compilation": "off"}
        # Even a query priced above the compiler's threshold must not compile
        # the many nested policy expressions in the combined Contacts query.
        cursor.execute("SET LOCAL jit_above_cost=0")
        cursor.execute("EXPLAIN (FORMAT JSON) " + contact_feed_sql(None) + " LIMIT 1", (None, None))
        assert "JIT" not in cursor.fetchone()["QUERY PLAN"][0]


def test_compilation_setting_does_not_change_operator_connections(request_workspace):
    _, operator_setting = request_workspace
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SHOW jit")
        assert cursor.fetchone()["jit"] == "off"
    set_workspace_id(None)
    require_workspace_scope(False)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SHOW jit")
        assert cursor.fetchone()["jit"] == operator_setting
