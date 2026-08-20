"""Writes against the three-axis contact state: who moves a contact, who raises
a flag, and the guarantees the split was made for. DB is mocked."""
from unittest.mock import MagicMock, patch

import pytest

from gcrm.tools import db_organizations


def make_mock_conn(rows=None):
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def executed_sql(cur):
    return " ".join(call.args[0] for call in cur.execute.call_args_list if call.args)


class TestSetOrganizationState:
    def test_writes_both_axes_in_one_statement(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db, patch("gcrm.tools.db_organizations.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.set_organization_state(
                7, pipeline_stage="opportunity", status="proposal", fit_score=80,
            )
        statement = cur.execute.call_args.args[0]
        assert "pipeline_stage = %s" in statement and "status = %s" in statement
        assert cur.execute.call_args.args[1][:2] == ("opportunity", "proposal")

    def test_coerces_an_unknown_value_instead_of_writing_it(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db, patch("gcrm.tools.db_organizations.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.set_organization_state(7, pipeline_stage="cold", status="accepted")
        assert cur.execute.call_args.args[1][:2] == ("candidate", "none")

    def test_keeps_the_existing_score_when_none_is_given(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db, patch("gcrm.tools.db_organizations.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.set_organization_state(7, pipeline_stage="suspect", status="ready")
        assert "COALESCE(%s, fit_score)" in cur.execute.call_args.args[0]


class TestSuppressionFlags:
    @pytest.mark.parametrize("flag", ["do_not_contact", "email_bounced", "research_exhausted"])
    def test_raises_each_known_flag(self, flag):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db, patch("gcrm.tools.db_organizations.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.set_suppression_flag(3, flag)
        assert f"SET {flag} = %s" in cur.execute.call_args.args[0]
        assert cur.execute.call_args.args[1] == (True, 3)

    def test_leaves_stage_and_status_untouched(self):
        """The reason for the split: a bounce must not cost you the meeting."""
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db, patch("gcrm.tools.db_organizations.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.set_suppression_flag(3, "email_bounced")
        statement = cur.execute.call_args.args[0]
        assert "pipeline_stage" not in statement and "status" not in statement

    def test_refuses_a_flag_name_it_does_not_know(self):
        """The name is interpolated into SQL, so an unchecked one is an injection."""
        with pytest.raises(ValueError):
            db_organizations.set_suppression_flag(3, "status = 'x'; DROP TABLE contacts; --")


class TestOutreachSelection:
    def test_excludes_suppressed_organizations(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.get_organizations_ready_for_outreach()
        statement = executed_sql(cur)
        assert "status = 'ready'" in statement
        assert "do_not_contact = FALSE" in statement
        assert "email_bounced = FALSE" in statement

    def test_candidates_are_selected_by_stage(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.get_candidates()
        assert "pipeline_stage = 'candidate'" in executed_sql(cur)

    def test_enrichment_skips_organizations_whose_research_is_exhausted(self):
        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_organizations.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_organizations.get_organizations_needing_enrichment()
        assert "research_exhausted = FALSE" in executed_sql(cur)


class TestOptOutAndBounce:
    def test_opt_out_raises_the_flag_and_logs_consent(self):
        from gcrm.tools import db_approvals

        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_approvals.db") as mock_db, patch("gcrm.tools.db_approvals.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_approvals.set_opt_out(11)
        statement = executed_sql(cur)
        assert "INSERT INTO consent_log" in statement
        assert "do_not_contact = TRUE" in statement
        assert "status = 'do_not_contact'" not in statement

    def test_compliance_check_reads_the_flag(self):
        from gcrm.tools import db_approvals

        conn, cur = make_mock_conn()
        cur.fetchone.side_effect = [
            {"opt_out": False, "erasure_requested": False},
            {"name": "Acme GmbH", "do_not_contact": True},
        ]
        with patch("gcrm.tools.db_approvals.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            assert db_approvals.check_compliance(11) is False

    def test_bounce_raises_the_flag_and_records_an_interaction(self):
        from gcrm.tools import db_inbox

        conn, cur = make_mock_conn()
        with patch("gcrm.tools.db_inbox.db") as mock_db, patch("gcrm.tools.db_inbox.log_audit"):
            mock_db.return_value.__enter__.return_value = conn
            db_inbox.mark_bad_email(5)
        statement = executed_sql(cur)
        assert "email_bounced = TRUE" in statement
        assert "INSERT INTO interactions" in statement
        assert "status = 'bad_email'" not in statement
