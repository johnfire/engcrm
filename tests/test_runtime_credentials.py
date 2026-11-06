"""Runtime DSN files fail closed and never fall back to privileged credentials."""
import os

import pytest
from psycopg2.extensions import parse_dsn

from gcrm.runtime_credentials import _runtime_dsn, resolve_database_url


def test_explicit_operator_connections_remain_supported_for_maintenance():
    assert resolve_database_url("postgresql://operator@db/crm", None) == "postgresql://operator@db/crm"


def test_credential_file_takes_precedence_and_requires_private_permissions(tmp_path):
    path = tmp_path / "database-dsn"
    credential = "postgresql://engcrm_app:" + "fictional-test-only-credential-1234567890" + "@db/crm"
    path.write_text(credential + "\n")
    os.chmod(path, 0o400)
    assert resolve_database_url("postgresql://operator@db/crm", str(path)) == credential
    os.chmod(path, 0o640)
    with pytest.raises(RuntimeError):
        resolve_database_url("postgresql://operator@db/crm", str(path))


def test_a_missing_or_empty_file_never_uses_the_operator_fallback(tmp_path):
    path = tmp_path / "database-dsn"
    with pytest.raises(FileNotFoundError):
        resolve_database_url("postgresql://operator@db/crm", str(path))
    path.write_text("")
    os.chmod(path, 0o400)
    with pytest.raises(RuntimeError):
        resolve_database_url("postgresql://operator@db/crm", str(path))
    with pytest.raises(RuntimeError):
        resolve_database_url(None, None)


def test_saved_runtime_credentials_cannot_silently_switch_database_targets(tmp_path):
    path = tmp_path / "database-dsn"
    path.write_text("host=other-db dbname=crm user=engcrm_app password=" + "a" * 48)
    path.chmod(0o400)
    with pytest.raises(RuntimeError, match="target"):
        _runtime_dsn("host=db dbname=crm user=operator password=fictional", path)


def test_runtime_file_cannot_supply_an_operator_login(tmp_path):
    path = tmp_path / "database-dsn"
    path.write_text("host=db dbname=crm user=operator password=" + "a" * 48)
    path.chmod(0o400)
    with pytest.raises(RuntimeError, match="runtime"):
        resolve_database_url(None, str(path))


def test_new_runtime_credentials_keep_the_target_but_never_the_operator_identity(tmp_path):
    generated = _runtime_dsn("host=db dbname=crm user=operator password=fictional sslmode=verify-full", tmp_path / "missing")
    parsed = parse_dsn(generated)
    assert parsed["user"] == "engcrm_app" and len(parsed["password"]) >= 32
    assert parsed["password"] != "fictional"
    assert (parsed["host"], parsed["dbname"], parsed["sslmode"]) == ("db", "crm", "verify-full")


def test_invalid_runtime_file_does_not_expose_its_contents_in_errors(tmp_path):
    path = tmp_path / "database-dsn"
    path.write_text("malformed-private-file-contents")
    path.chmod(0o400)
    with pytest.raises(RuntimeError) as failure:
        resolve_database_url(None, str(path))
    assert "malformed-private-file-contents" not in str(failure.value)
