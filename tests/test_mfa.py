"""Authenticator vectors and the shared password/second-factor boundary."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from gcrm.api.auth import authenticate_login
from gcrm.api.security import hash_password
from gcrm.api.totp import (
    build_totp_uri,
    generate_totp_secret,
    matching_totp_counter,
    verify_totp_code,
)


@pytest.mark.parametrize("timestamp,expected", [(59, "287082"), (1111111109, "081804"), (1234567890, "005924")])
def test_totp_matches_rfc6238_sha1_six_digit_vectors(timestamp, expected):
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert matching_totp_counter(secret, expected, timestamp) == timestamp // 30
    assert verify_totp_code(secret, expected, timestamp)
    assert not verify_totp_code(secret, expected, timestamp + 120)


@pytest.mark.parametrize("code", ["", "12345", "1234567", "１２３４５６", "abcdef"])
def test_totp_rejects_malformed_codes(code):
    assert matching_totp_counter("JBSWY3DPEHPK3PXP", code, 1234567890) is None


def test_setup_secrets_are_random_and_uris_encode_the_account_label():
    first, second = generate_totp_secret(), generate_totp_secret()
    assert len(first) == 32 and first != second
    uri = build_totp_uri(first, "person+test@example.test")
    assert "person%2Btest%40example.test" in uri
    assert f"secret={first}" in uri
    assert "period=30" in uri and "digits=6" in uri


@pytest.fixture
def enabled_account():
    return {"id": 7, "email": "person@example.test", "is_active": True, "role": "admin",
            "workspace_id": 3, "password_hash": hash_password("password"), "mfa_enabled": True,
            "token_version": 4}


def test_password_failure_never_attempts_or_consumes_a_second_factor(enabled_account):
    with patch("gcrm.api.auth.verify_login_factor") as verify:
        assert authenticate_login(enabled_account["email"], "wrong", enabled_account, "123456") is None
    verify.assert_not_called()


@pytest.mark.parametrize("verified", [True, False])
def test_enabled_accounts_require_success_from_the_shared_factor_boundary(enabled_account, verified):
    with patch("gcrm.api.auth.verify_login_factor", return_value=verified) as verify:
        payload = authenticate_login(enabled_account["email"], "password", enabled_account, "123456")
    verify.assert_called_once_with(7, "123456", 4)
    assert (payload is not None) is verified


def test_factor_storage_failures_are_unavailable_not_authenticated(enabled_account):
    with patch("gcrm.api.auth.verify_login_factor", side_effect=RuntimeError("DB unavailable")):
        with pytest.raises(HTTPException) as exception:
            authenticate_login(enabled_account["email"], "password", enabled_account, "123456")
    assert exception.value.status_code == 503
