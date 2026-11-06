"""Prepare private web settings without handing the web process operator credentials."""
import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from gcrm.config_security import is_weak_secret, validate_deployment_security

OPERATOR_PREFIXES = ("POSTGRES_", "DATABASE_", "TEST_DATABASE_", "PG", "RUNTIME_", "VPS_", "GHCR_", "DOCKER_")


def runtime_settings(source: Path) -> dict[str, str]:
    settings = {key: value for key, value in dotenv_values(source).items() if value is not None
                and not key.startswith(OPERATOR_PREFIXES) and key != "ENGCRM_IMAGE"}
    for name in ("JWT_SECRET", "SESSION_SECRET", "ACCOUNT_ENCRYPTION_KEY"):
        value = settings.get(name, settings.get("SESSION_SECRET", "") if name == "ACCOUNT_ENCRYPTION_KEY" else "")
        if is_weak_secret(value):
            raise RuntimeError(f"{name} must contain at least 32 bytes of strong random material")
    validate_deployment_security("production", settings["JWT_SECRET"], settings["SESSION_SECRET"],
                                 settings.get("APP_PUBLIC_URL", ""), settings.get("SESSION_COOKIE_SECURE") == "true")
    return {**settings, "APP_ENV": "production", "PYTHON_DOTENV_DISABLED": "1"}


def write_runtime_environment(source: Path, target: Path) -> None:
    settings = runtime_settings(source)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            for name, value in settings.items():
                quoted = value.replace("'", "\\'")
                output.write(f"{name}='{quoted}'\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
