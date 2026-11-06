"""Runtime credentials cannot perform migration/operator database operations."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

import psycopg2
import pytest
from fastapi.testclient import TestClient
from psycopg2.extensions import parse_dsn

from gcrm.api.main import app
from gcrm.api.security import encrypt_totp_secret, hash_password
from gcrm.api.totp import _totp_code
from gcrm.config import ACCOUNT_ENCRYPTION_KEY
from gcrm.db.connection import db
from gcrm.runtime_credentials import provision_runtime_credentials
from gcrm.tools.db_users import create_user

pytestmark = [pytest.mark.integration, pytest.mark.security_boundary]


class PrivateDsn(str):
    def __repr__(self):
        return "<private disposable runtime DSN>"


def test_migrations_create_a_limited_runtime_role(migrated_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                       "FROM pg_roles WHERE rolname='engcrm_app'")
        role = cursor.fetchone()
    assert role is not None, "The deployed app needs credentials distinct from the bootstrap account"
    assert all(flag is False for flag in role.values())


@pytest.fixture
def runtime_dsn(migrated_database, tmp_path):
    path = tmp_path / "database-dsn"
    provision_runtime_credentials(migrated_database, path)
    first = path.read_text()
    provision_runtime_credentials(migrated_database, path)
    assert path.read_text() == first  # Deployments do not silently rotate a live credential.
    assert path.stat().st_mode & 0o777 == 0o400
    assert parse_dsn(first)["user"] == "engcrm_app"
    assert parse_dsn(first)["password"] != parse_dsn(migrated_database)["password"]
    return PrivateDsn(first.strip())


def test_runtime_provisioning_refuses_membership_in_an_operator_role(migrated_database, tmp_path):
    with db() as connection:
        connection.cursor().execute("GRANT artcrm_admindude TO engcrm_app")
    try:
        with pytest.raises(RuntimeError, match="membership"):
            provision_runtime_credentials(migrated_database, tmp_path / "database-dsn")
    finally:
        with db() as connection:
            connection.cursor().execute("REVOKE artcrm_admindude FROM engcrm_app")


@pytest.mark.parametrize("statement", ["CREATE TABLE forbidden_table(id INTEGER)",
                                        "ALTER TABLE contacts DISABLE ROW LEVEL SECURITY",
                                        "SELECT * FROM contacts", "SET ROLE artcrm_admindude"])
def test_runtime_connection_cannot_use_operator_privileges(runtime_dsn, statement):
    connection = psycopg2.connect(runtime_dsn)
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            connection.cursor().execute(statement)
    finally:
        connection.rollback()
        connection.close()


def test_real_runtime_credentials_support_mfa_and_keep_workspace_boundaries(clean_database, runtime_dsn, monkeypatch):
    password, email, seed = "Fictional-runtime-password", "runtime@example.test", "JBSWY3DPEHPK3PXP"
    user_id = create_user(email, hash_password(password))
    recovery = ["fictionalrecoveryone", "fictionalrecoverytwo"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE users SET mfa_enabled=TRUE,mfa_secret_encrypted=%s,mfa_recovery_hashes=%s WHERE id=%s",
                       (encrypt_totp_secret(seed, ACCOUNT_ENCRYPTION_KEY),
                        [hashlib.sha256(code.encode()).hexdigest() for code in recovery], user_id))
        cursor.execute("INSERT INTO workspaces(name,slug) VALUES ('Fictional Foreign','runtime-foreign') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        foreign_workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO people(name,workspace_id) VALUES ('Foreign Person',%s) RETURNING id", (foreign_workspace,))
        foreign_person = cursor.fetchone()["id"]
    monkeypatch.setattr("gcrm.db.connection.DATABASE_URL", runtime_dsn)
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    response = client.post("/api/auth/token", json={"email": email, "password": password,
                                                   "mfa_code": _totp_code(seed, int(time.time()))})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get(f"/api/people/{foreign_person}", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    page = client.get("/login")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    client.headers.update({"Origin": "https://testserver", "X-CSRF-Token": csrf})
    assert client.post("/login", data={"email": email, "password": password, "mfa_code": recovery[0]}).status_code == 303
    page = client.get("/settings/two-factor")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    response = client.post("/settings/two-factor/recovery", data={"current_password": password,
                           "mfa_code": recovery[1]}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    assert len(re.findall(r'<li><code>([a-f0-9]{32})</code>', response.text)) == 10
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_runtime_background_snapshots_cover_workspaces_without_operator_credentials(clean_database, runtime_dsn, monkeypatch):
    from gcrm.tools.statistics_history import record_all_workspace_snapshots

    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces(name,slug) VALUES ('Fictional Snapshot','runtime-snapshots') "
                       "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id")
        workspace = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO contacts(name,workspace_id) VALUES ('Snapshot Factory',%s) RETURNING id", (workspace,))
        organization = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO deals(workspace_id,contact_id,offer_id,pipeline_stage,status) "
                       "VALUES (%s,%s,offer_id_for(%s,'consulting'),'candidate','ready')", (workspace, organization, workspace))
    with monkeypatch.context() as runtime_context:
        runtime_context.setattr("gcrm.db.connection.DATABASE_URL", runtime_dsn)
        assert record_all_workspace_snapshots() >= 1
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT n FROM pipeline_snapshots WHERE workspace_id=%s", (workspace,))
        assert cursor.fetchone()["n"] == 1


def test_runtime_maintenance_commands_enter_the_default_workspace(clean_database, runtime_dsn):
    environment = {**os.environ, "DATABASE_URL": runtime_dsn, "PYTHON_DOTENV_DISABLED": "1"}
    command = subprocess.run([sys.executable, "-m", "scripts.workspace_command", "scripts/maps/pin_queue.py", "--limit", "1"],
                             env=environment, capture_output=True, text=True, timeout=20)
    assert command.returncode == 0, command.stderr
    assert json.loads(command.stdout) == []
