"""Small hardening fixes: SSRF ranges, LIKE escaping, MCP token role, audit-script TLS."""
from unittest.mock import MagicMock, patch

import pytest

from gcrm.tools.like import escape_like
from gcrm.tools.search import is_public_http_url


@pytest.mark.parametrize("url", ["http://100.64.0.1/", "http://100.127.255.254/", "http://198.18.0.1/",
                                 "http://192.0.0.8/"])
def test_shared_and_special_use_address_ranges_are_not_public(url):
    assert is_public_http_url(url) is False


def test_an_ordinary_public_address_is_still_allowed():
    assert is_public_http_url("http://8.8.8.8/") is True


def test_escape_like_takes_the_wildcards_literally():
    assert escape_like("a_b%c!d") == "a!_b!%c!!d"
    assert escape_like("plain.example") == "plain.example"


def fake_db(rows):
    """A db() stand-in whose cursor returns `rows` in order and records every execute()."""
    cursor = MagicMock()
    cursor.fetchone.side_effect = rows
    connection = MagicMock()
    connection.cursor.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return MagicMock(return_value=context), cursor


def test_the_domain_fallback_for_inbound_mail_escapes_wildcards():
    from gcrm.tools import db_organizations
    factory, cursor = fake_db([None, None])
    with patch.object(db_organizations, "db", factory):
        db_organizations.match_organization_by_email("x@a%b.de")
    sql, params = cursor.execute.call_args_list[1].args
    assert "ESCAPE '!'" in sql
    assert params == ("%@a!%b.de",)


def test_the_domain_fallback_for_scanned_cards_escapes_wildcards():
    from gcrm.tools import cards
    factory, cursor = fake_db([None, None, None, None, None])
    with patch("gcrm.db.connection.db", factory):
        cards.find_possible_duplicate({"email": "x@a_b.de"})
    sql, params = cursor.execute.call_args_list[1].args
    assert "ESCAPE '!'" in sql
    assert params == ("%@a!_b.de",)


def test_a_connector_token_only_works_for_an_admin_account():
    from gcrm.mcp import tokens
    factory, cursor = fake_db([None])
    with patch.object(tokens, "db", factory):
        assert tokens.verify_token("engcrm_abc") is None
    sql = cursor.execute.call_args.args[0]
    assert "u.role = 'admin'" in sql


def test_the_sent_folder_audit_upgrades_to_tls_before_it_logs_in():
    from gcrm.supervisor import run_email_audit
    imap = MagicMock()
    imap.search.return_value = (None, [b""])
    with patch.object(run_email_audit.imaplib, "IMAP4", return_value=imap):
        run_email_audit.fetch_sent_recipients("mail.example.test", 143, "user", "secret")
    names = [call[0] for call in imap.method_calls]
    assert names.index("starttls") < names.index("login")
