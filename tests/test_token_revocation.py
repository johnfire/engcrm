"""Mobile bearer-token revocation via per-user token_version."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from gcrm.api.jwt_auth import create_token, decode_token, require_jwt


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_decode_token_still_returns_role_for_user_token():
    token = create_token("admin", user_id=7, token_version=3)
    assert decode_token(token) == "admin"


def test_matching_version_is_accepted():
    token = create_token("spectator", user_id=7, token_version=3)
    with patch("gcrm.api.jwt_auth.get_user_token_version", return_value=3):
        assert require_jwt(_creds(token)) == "spectator"


def test_stale_version_is_rejected():
    token = create_token("admin", user_id=7, token_version=3)
    with patch("gcrm.api.jwt_auth.get_user_token_version", return_value=4):
        with pytest.raises(HTTPException) as exc:
            require_jwt(_creds(token))
        assert exc.value.status_code == 401


def test_disabled_or_missing_user_is_rejected():
    token = create_token("admin", user_id=7, token_version=0)
    with patch("gcrm.api.jwt_auth.get_user_token_version", return_value=None):
        with pytest.raises(HTTPException) as exc:
            require_jwt(_creds(token))
        assert exc.value.status_code == 401


def test_legacy_token_without_uid_skips_db_check():
    # Break-glass / legacy tokens carry no uid and must not hit the DB.
    token = create_token("admin")
    with patch("gcrm.api.jwt_auth.get_user_token_version",
               side_effect=AssertionError("must not be called for a uid-less token")):
        assert require_jwt(_creds(token)) == "admin"


def test_version_check_fails_open_on_db_error():
    token = create_token("admin", user_id=7, token_version=0)
    with patch("gcrm.api.jwt_auth.get_user_token_version", side_effect=RuntimeError("db down")):
        assert require_jwt(_creds(token)) == "admin"
