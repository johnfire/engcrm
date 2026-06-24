"""STARTTLS context: verify remote certs, skip for the local Proton Bridge."""
import ssl

from gcrm.tools.email import _starttls_context


def test_loopback_skips_verification():
    ctx = _starttls_context("127.0.0.1")
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_remote_host_verifies():
    ctx = _starttls_context("mail.example.com")
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
