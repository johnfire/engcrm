"""Help Centre access controls, customer rendering, and editor validation."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login

client = TestClient(main.app)


@pytest.fixture
def signed_in_customer():
    main.app.dependency_overrides[require_login] = lambda: "spectator"
    yield
    main.app.dependency_overrides.pop(require_login, None)


@pytest.fixture
def signed_in_admin():
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_admin, None)


def test_help_centre_renders_published_articles(signed_in_customer):
    articles = [{"id": 7, "slug": "approvals", "category": "outreach", "title": "Review safely", "summary": "Drafts first", "body": "Nothing sends automatically."}]
    with patch("gcrm.api.routers.help.list_published_help", return_value=articles), \
         patch("gcrm.api.routers.help.has_completed_help_tour", return_value=True):
        response = client.get("/help/?lang=en")
    assert response.status_code == 200
    assert "Review safely" in response.text
    assert "Nothing sends automatically." in response.text


def test_help_editor_requires_admin():
    response = client.get("/help/manage", follow_redirects=False)
    assert response.status_code in (303, 307, 401, 403)


def test_help_editor_saves_bilingual_published_article(signed_in_admin):
    fields = {
        "slug": "safe-research", "category": "research", "status": "published",
        "surface_web": "on", "surface_mobile": "on",
        "title_en": "Safe research", "title_de": "Sichere Recherche",
        "summary_en": "Queue work", "summary_de": "Arbeit einreihen",
        "body_en": "No email is sent.", "body_de": "Keine E-Mail wird versendet.",
    }
    with patch("gcrm.api.routers.help.save_help_article", return_value=9) as save:
        response = client.post("/help/manage", data=fields, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/help/manage"
    saved = save.call_args.args[1]
    assert saved["slug"] == "safe-research"
    assert saved["surfaces"] == ["web", "mobile"]


def test_help_editor_rejects_missing_translation(signed_in_admin):
    fields = {
        "slug": "safe-research", "category": "research", "status": "draft", "surface_web": "on",
        "title_en": "Safe research", "title_de": "", "body_en": "Body", "body_de": "",
    }
    with patch("gcrm.api.routers.help.save_help_article") as save:
        response = client.post("/help/manage", data=fields, follow_redirects=False)
    assert response.status_code == 303
    assert not save.called
