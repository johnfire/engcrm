"""Changing an organization's stage straight from the Organizations list."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login

client = TestClient(main.app)


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def _post_stage(stage: str, rowcount: int = 1, next_url: str = "/organizations/?stage=suspect&page=2"):
    cursor = MagicMock()
    cursor.rowcount = rowcount
    with patch("gcrm.api.routers.organizations.db") as mock_db, \
         patch("gcrm.api.routers.organizations.log_audit") as audit:
        mock_db.return_value.__enter__.return_value.cursor.return_value = cursor
        response = client.post("/organizations/7/stage", data={"stage": stage, "next": next_url},
                               follow_redirects=False)
    return response, cursor, audit


def test_picking_a_stage_saves_only_the_stage_and_returns_to_the_same_list(admin_web):
    response, cursor, audit = _post_stage("prospect")

    assert response.status_code == 303
    assert response.headers["location"] == "/organizations/?stage=suspect&page=2"
    sql, params = cursor.execute.call_args.args
    assert sql.startswith("UPDATE contacts SET pipeline_stage = %s, updated_at = NOW()")
    assert "status" not in sql and "deleted_at IS NULL" in sql
    assert params == ("prospect", 7)
    audit.assert_called_once_with(None, None, "contact.stage_changed", "contact:7", "prospect")


@pytest.mark.parametrize("stage", ["", "bogus"])
def test_an_unknown_stage_is_refused_and_nothing_is_written(admin_web, stage):
    response, cursor, audit = _post_stage(stage)

    assert response.status_code == 400
    cursor.execute.assert_not_called()
    audit.assert_not_called()


def test_a_missing_organization_is_a_404(admin_web):
    response, _, audit = _post_stage("customer", rowcount=0)

    assert response.status_code == 404
    audit.assert_not_called()


def test_an_offsite_next_url_does_not_redirect_away(admin_web):
    response, _, _ = _post_stage("customer", next_url="https://evil.example/")

    assert response.headers["location"] == "/organizations/"
