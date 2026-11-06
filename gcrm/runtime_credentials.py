"""Provision a separate runtime login and atomically preserve its private DSN."""
import os
import secrets
import tempfile
from contextlib import closing
from pathlib import Path

import psycopg2
from psycopg2.extensions import make_dsn, parse_dsn

RUNTIME_ROLE = "engcrm_app"


def resolve_database_url(configured: str | None, credential_file: str | None) -> str:
    """An explicitly configured credential file must exist; never fall back to an operator DSN."""
    if credential_file:
        path = Path(credential_file)
        if path.stat().st_mode & 0o077:
            raise RuntimeError("Runtime database credential file must not be group/world accessible")
        configured = path.read_text().strip()
        try:
            parameters = parse_dsn(configured)
        except psycopg2.ProgrammingError:
            raise RuntimeError("Invalid runtime database credentials") from None
        if parameters.get("user") != RUNTIME_ROLE or len(parameters.get("password", "")) < 32:
            raise RuntimeError("The runtime file must contain a private engcrm_app login")
    if not configured:
        raise RuntimeError("Set DATABASE_URL or a readable DATABASE_URL_FILE")
    return configured


def _runtime_dsn(operator_dsn: str, credential_file: Path) -> str:
    if credential_file.exists():
        existing = resolve_database_url(None, str(credential_file))
        parsed = parse_dsn(existing)
        if parsed.get("user") != RUNTIME_ROLE or len(parsed.get("password", "")) < 32:
            raise RuntimeError("Existing runtime credentials are not a strong engcrm_app login")
        target = {key: value for key, value in parse_dsn(operator_dsn).items() if key not in {"user", "password"}}
        saved_target = {key: value for key, value in parsed.items() if key not in {"user", "password"}}
        if target != saved_target:
            raise RuntimeError("Saved runtime credentials target a different database; review configuration before deployment")
        return existing
    parameters = parse_dsn(operator_dsn)
    parameters.update(user=RUNTIME_ROLE, password=secrets.token_urlsafe(48))
    return make_dsn(**parameters)


def _write_private_dsn(credential_file: Path, dsn: str) -> None:
    credential_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=credential_file.parent, delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o400)
            output.write(dsn + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, credential_file)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def provision_runtime_credentials(operator_dsn: str, credential_file: Path) -> None:
    """Keep the same secret across deployments; refuse dangerous role definitions."""
    dsn = _runtime_dsn(operator_dsn, credential_file)
    password = parse_dsn(dsn)["password"]
    with closing(psycopg2.connect(operator_dsn)) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit "
                           "FROM pg_roles WHERE rolname=%s", (RUNTIME_ROLE,))
            flags = cursor.fetchone()
            if flags is None or any(flags):
                raise RuntimeError("Migrate first; the runtime role must not have operator privileges")
            cursor.execute("SELECT rolname FROM pg_roles WHERE pg_has_role(%s,oid,'MEMBER') "
                           "AND rolname NOT IN (%s,'engcrm_workspace')", (RUNTIME_ROLE, RUNTIME_ROLE))
            if cursor.fetchone() is not None:
                raise RuntimeError("Runtime role has an unexpected role membership")
            cursor.execute("ALTER ROLE engcrm_app LOGIN PASSWORD %s", (password,))
    _write_private_dsn(credential_file, dsn)
