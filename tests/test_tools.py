"""
Unit tests for concrete tool implementations.
The database is mocked so these run without a live PostgreSQL connection.
"""
from unittest.mock import MagicMock, patch


def make_mock_conn(rows=None, rowcount=1):
    """Return a mock psycopg2 connection that returns `rows` from fetchall/fetchone."""
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    cur.rowcount = rowcount

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestSaveContact:
    def test_inserts_new_contact(self):
        from gcrm.tools.db import save_contact
        conn, cur = make_mock_conn()
        # First fetchone = no duplicate; second = RETURNING id; third = no existing consent_log
        cur.fetchone.side_effect = [None, {"id": 42}, None]

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            result = save_contact("Galerie Nord", "Munich", country="DE", type="gallery")

        assert result == 42
        assert cur.execute.call_count >= 2

    def test_returns_zero_on_duplicate(self):
        from gcrm.tools.db import save_contact
        conn, cur = make_mock_conn()
        cur.fetchone.return_value = {"id": 7}  # duplicate found

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            result = save_contact("Galerie Nord", "Munich")

        # 0 = "not newly created". The research agent and import_studies both rely
        # on a falsy return to skip/count duplicates instead of re-processing them.
        assert result == 0


class TestCheckCompliance:
    def test_blocks_opted_out_contact(self):
        from gcrm.tools.db import check_compliance
        conn, cur = make_mock_conn()
        cur.fetchone.return_value = {"opt_out": True, "erasure_requested": False}

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            result = check_compliance(contact_id=1)

        assert result is False

    def test_blocks_erased_contact(self):
        from gcrm.tools.db import check_compliance
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [
            {"opt_out": False, "erasure_requested": False},
            {"name": "[removed]"},
        ]

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            result = check_compliance(contact_id=2)

        assert result is False

    def test_allows_clean_contact(self):
        from gcrm.tools.db import check_compliance
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [
            {"opt_out": False, "erasure_requested": False},
            {"name": "Galerie Nord", "status": "cold"},
        ]

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            result = check_compliance(contact_id=3)

        assert result is True

    def test_allows_contact_with_no_consent_log(self):
        from gcrm.tools.db import check_compliance
        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [
            None,                    # no consent_log row
            {"name": "Galerie Sud", "status": "cold"},
        ]

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            result = check_compliance(contact_id=4)

        assert result is True


class TestSetOptOut:
    def test_inserts_consent_log_row(self):
        from gcrm.tools.db import set_opt_out
        conn, cur = make_mock_conn()

        with patch("gcrm.tools.db.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            set_opt_out(contact_id=5)

        # Should have called execute at least twice (INSERT + UPDATE)
        assert cur.execute.call_count >= 2
        # One of the calls should reference 'opt_out'
        calls_sql = " ".join(str(c) for c in cur.execute.call_args_list)
        assert "opt_out" in calls_sql.lower()


class TestLlmBackends:
    def test_supports_deepseek_when_administrator_selects_it(self):
        from gcrm.tools.llm import get_llm

        assert get_llm("deepseek-chat") is not None


class TestAiBackendSettings:
    def test_rejects_a_model_outside_the_selectable_allowlist(self):
        from gcrm.tools.db_ai_backends import set_ai_backends

        try:
            set_ai_backends("unknown", "claude")
        except ValueError as error:
            assert "Unsupported" in str(error)
        else:
            raise AssertionError("Unsupported AI backend was accepted")


class TestStartFinishRun:
    def test_start_run_returns_id(self):
        from gcrm.tools.db import start_run
        conn, cur = make_mock_conn()
        cur.fetchone.return_value = {"id": 99}

        with patch("gcrm.tools.db_agent_runs.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            run_id = start_run("test_agent", {"key": "value"})

        assert run_id == 99

    def test_finish_run_updates_record(self):
        from gcrm.tools.db import finish_run
        conn, cur = make_mock_conn()

        with patch("gcrm.tools.db_agent_runs.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            finish_run(99, "completed", "all done", {"count": 5})

        sql_calls = [str(call_obj) for call_obj in cur.execute.call_args_list]
        assert any("UPDATE" in sql for sql in sql_calls)
