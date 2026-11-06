"""The generated web environment retains app settings, never owner credentials."""
import secrets

import pytest
from dotenv import dotenv_values

from gcrm.deployment_environment import write_runtime_environment


def operator_environment(path):
    path.write_text("\n".join([
        f"JWT_SECRET={secrets.token_hex(32)}", f"SESSION_SECRET={secrets.token_hex(32)}",
        "APP_PUBLIC_URL=https://crm.example.test", "SESSION_COOKIE_SECURE=true",
        "POSTGRES_USER=operator", "POSTGRES_PASSWORD=private-owner-password",
        "DATABASE_URL=postgresql://operator:private-owner-password@db/gcrm",
        "PGPASSWORD=private-owner-password", "MAIL_PASSWORD='application mail password'",
        "CHEAP_LLM=deepseek-chat", "EMAIL_ENABLED=false",
    ]))


def test_runtime_settings_are_private_and_exclude_all_database_owner_values(tmp_path):
    source, target = tmp_path / "operator.env", tmp_path / "app.env"
    operator_environment(source)
    write_runtime_environment(source, target)
    settings = dotenv_values(target)
    assert settings["MAIL_PASSWORD"] == "application mail password"
    assert settings["CHEAP_LLM"] == "deepseek-chat"
    assert settings["APP_ENV"] == "production"
    assert not any(key.startswith(("POSTGRES_", "DATABASE_", "PG")) for key in settings)
    assert "private-owner-password" not in target.read_text()
    assert target.stat().st_mode & 0o777 == 0o600
    first = target.read_text()
    write_runtime_environment(source, target)
    assert target.read_text() == first


def test_unsafe_operator_settings_leave_existing_runtime_environment_untouched(tmp_path):
    source, target = tmp_path / "operator.env", tmp_path / "app.env"
    operator_environment(source)
    source.write_text(source.read_text().replace("SESSION_COOKIE_SECURE=true", "SESSION_COOKIE_SECURE=false"))
    target.write_text("previous-good-environment")
    with pytest.raises(RuntimeError):
        write_runtime_environment(source, target)
    assert target.read_text() == "previous-good-environment"
