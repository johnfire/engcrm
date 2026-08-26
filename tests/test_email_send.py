"""send_email(): SMTP delivery plus a best-effort IMAP copy into the Sent
folder. Network calls (smtplib, imaplib) are mocked — runs without a real
mail server."""
from unittest.mock import MagicMock, patch

from gcrm.tools import email as email_tools


def test_disabled_returns_false():
    with patch.object(email_tools, "EMAIL_ENABLED", False):
        assert email_tools.send_email("a@b.com", "Subject", "Body") is False


def test_missing_recipient_or_body_returns_false():
    with patch.object(email_tools, "EMAIL_ENABLED", True):
        assert email_tools.send_email("", "Subject", "Body") is False
        assert email_tools.send_email("a@b.com", "Subject", "") is False


def test_successful_send_sets_headers_and_appends_to_sent():
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_imap = MagicMock()
    fake_imap.__enter__.return_value = fake_imap

    with patch.object(email_tools, "EMAIL_ENABLED", True), \
         patch.object(email_tools.smtplib, "SMTP", return_value=fake_smtp), \
         patch.object(email_tools.imaplib, "IMAP4", return_value=fake_imap):
        result = email_tools.send_email("anna@example.com", "Curious", "Hi Anna")

    assert result is True
    fake_smtp.login.assert_called_once()
    sent_msg = fake_smtp.sendmail.call_args.args[2]
    assert "Date:" in sent_msg
    assert "Message-ID:" in sent_msg

    fake_imap.login.assert_called_once()
    append_args = fake_imap.append.call_args.args
    assert append_args[0] == "Sent"


def test_from_email_override_used_in_from_header():
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp

    with patch.object(email_tools, "EMAIL_ENABLED", True), \
         patch.object(email_tools.smtplib, "SMTP", return_value=fake_smtp), \
         patch.object(email_tools, "_append_to_sent"):
        email_tools.send_email("anna@example.com", "Subj", "Body", from_email="contact@christopherrehm.de")

    sent_msg = fake_smtp.sendmail.call_args.args[2]
    assert "From: contact@christopherrehm.de" in sent_msg


def test_sent_folder_append_failure_does_not_fail_the_send():
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp

    with patch.object(email_tools, "EMAIL_ENABLED", True), \
         patch.object(email_tools.smtplib, "SMTP", return_value=fake_smtp), \
         patch.object(email_tools.imaplib, "IMAP4", side_effect=RuntimeError("imap down")):
        result = email_tools.send_email("anna@example.com", "Subj", "Body")

    assert result is True


def test_smtp_failure_returns_false_and_skips_sent_append():
    with patch.object(email_tools, "EMAIL_ENABLED", True), \
         patch.object(email_tools.smtplib, "SMTP", side_effect=RuntimeError("smtp down")), \
         patch.object(email_tools, "_append_to_sent") as append:
        result = email_tools.send_email("anna@example.com", "Subj", "Body")

    assert result is False
    append.assert_not_called()
