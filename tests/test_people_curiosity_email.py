"""Person-scoped, non-sales first-contact email: LLM-authored observation
assembled into a fixed template, plus the draft/send web routes. DB and LLM
are mocked — runs without Postgres. See
docs/plans/2026-08-26-person-curiosity-email-design.md."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_admin, require_login
from gcrm.tools import curiosity_email

client = TestClient(main.app)

PERSON = {
    "id": 3, "name": "Anna Roth", "title": "Kuratorin", "email": "anna@galerie-nord.de",
    "notes": "Interested in AI for exhibition logistics.", "contact_id": None,
    "relationship": None, "city": "Augsburg",
}
PERSON_LINKED = {**PERSON, "contact_id": 42}
ORGANIZATION = {
    "id": 42, "name": "Galerie Nord", "type": "Kunstgalerie", "city": "Augsburg",
    "notes": "Runs three shows a year.", "website": "https://galerie-nord.de",
}


@pytest.fixture
def admin_web():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[require_admin] = lambda: "admin"
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(require_admin, None)


def _fake_llm(observation_json: str) -> MagicMock:
    resp = MagicMock()
    resp.content = observation_json
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = resp
    return fake_llm


class TestDraftCuriosityEmail:
    def test_success_person_only_english(self):
        with patch("gcrm.tools.db_people.get_person", return_value=PERSON), \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm",
                   return_value=_fake_llm('{"observation": "You mentioned wanting to streamline exhibition logistics."}')):
            out = curiosity_email.draft_curiosity_email(3, "en")
        assert "My name is Christopher Rehm" in out["body"]
        assert "October 1, 2026" in out["body"]
        assert "streamline exhibition logistics" in out["body"]
        assert out["subject"] == "Curious how you see AI affecting Kuratorin"

    def test_success_with_linked_organization_and_german(self):
        with patch("gcrm.tools.db_people.get_person", return_value=PERSON_LINKED), \
             patch("gcrm.tools.db_organizations.get_organization", return_value=ORGANIZATION) as get_org, \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm",
                   return_value=_fake_llm('{"observation": "Sie veranstalten drei Ausstellungen pro Jahr."}')):
            out = curiosity_email.draft_curiosity_email(3, "de")
        get_org.assert_called_once_with(42)
        assert "Mein Name ist Christopher Rehm" in out["body"]
        assert "1. Oktober 2026" in out["body"]
        # field comes from the linked organization's type, not the person's title
        assert out["subject"] == "Ihre Einschätzung zu KI in Kunstgalerie"

    def test_no_organization_falls_back_to_title(self):
        with patch("gcrm.tools.db_people.get_person", return_value=PERSON), \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm", return_value=_fake_llm('{"observation": "x"}')):
            out = curiosity_email.draft_curiosity_email(3, "en")
        assert "Kuratorin" in out["subject"]

    def test_no_title_or_organization_uses_field_fallback(self):
        bare = {**PERSON, "title": None}
        with patch("gcrm.tools.db_people.get_person", return_value=bare), \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm", return_value=_fake_llm('{"observation": "x"}')):
            out = curiosity_email.draft_curiosity_email(3, "en")
        assert "your line of work" in out["subject"]

    def test_generation_failure_returns_fixed_error(self):
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("boom")
        with patch("gcrm.tools.db_people.get_person", return_value=PERSON), \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm", return_value=fake_llm):
            out = curiosity_email.draft_curiosity_email(3)
        # The upstream message is logged, never handed to the client.
        assert out == {"error": curiosity_email.DRAFT_FAILED}

    def test_malformed_llm_json_returns_fixed_error(self):
        with patch("gcrm.tools.db_people.get_person", return_value=PERSON), \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm", return_value=_fake_llm("not json at all")):
            out = curiosity_email.draft_curiosity_email(3)
        assert out == {"error": curiosity_email.DRAFT_FAILED}

    def test_missing_person_raises_lookup_error(self):
        with patch("gcrm.tools.db_people.get_person", return_value=None):
            with pytest.raises(LookupError):
                curiosity_email.draft_curiosity_email(999)

    def test_unknown_language_defaults_to_english_template(self):
        with patch("gcrm.tools.db_people.get_person", return_value=PERSON), \
             patch("gcrm.tools.db_people_interactions.get_person_interactions", return_value=[]), \
             patch("gcrm.tools.llm.get_llm", return_value=_fake_llm('{"observation": "x"}')):
            out = curiosity_email.draft_curiosity_email(3, "fr")
        assert "My name is Christopher Rehm" in out["body"]


class TestCuriosityEmailDraftRoute:
    """Drafting now queues the email straight into the held-drafts pipeline
    (approval_queue, status=on_hold) instead of returning it for inline
    editing — review and sending happen on the Drafts page. See
    docs/plans/2026-08-26-person-curiosity-email-design.md."""

    def test_requires_auth(self):
        resp = client.post("/people/3/curiosity-email/draft", follow_redirects=False)
        assert resp.status_code == 307

    def test_success_queues_a_draft(self, admin_web):
        with patch(
            "gcrm.api.routers.people.draft_curiosity_email",
            return_value={"subject": "Curious...", "body": "Hi Anna,..."},
        ) as draft, \
             patch("gcrm.api.routers.people.queue_person_draft", return_value=77) as queue, \
             patch("gcrm.api.routers.people.log_audit"):
            resp = client.post("/people/3/curiosity-email/draft?language=de")
        assert resp.status_code == 200
        assert resp.json() == {"draft_id": 77}
        draft.assert_called_once_with(3, "de")
        queue.assert_called_once_with(3, "Curious...", "Hi Anna,...")

    def test_invalid_language_falls_back_to_english(self, admin_web):
        with patch(
            "gcrm.api.routers.people.draft_curiosity_email",
            return_value={"subject": "x", "body": "y"},
        ) as draft, \
             patch("gcrm.api.routers.people.queue_person_draft", return_value=1), \
             patch("gcrm.api.routers.people.log_audit"):
            client.post("/people/3/curiosity-email/draft?language=fr")
        draft.assert_called_once_with(3, "en")

    def test_missing_person_is_404(self, admin_web):
        with patch("gcrm.api.routers.people.draft_curiosity_email", side_effect=LookupError()):
            resp = client.post("/people/999/curiosity-email/draft")
        assert resp.status_code == 404

    def test_generation_failure_surfaces_fixed_error_and_does_not_queue(self, admin_web):
        with patch(
            "gcrm.api.routers.people.draft_curiosity_email",
            return_value={"error": curiosity_email.DRAFT_FAILED},
        ), patch("gcrm.api.routers.people.queue_person_draft") as queue:
            resp = client.post("/people/3/curiosity-email/draft")
        assert resp.status_code == 200
        assert resp.json()["error"] == curiosity_email.DRAFT_FAILED
        queue.assert_not_called()


def test_person_template_has_curiosity_email_section():
    template = (Path(__file__).parents[1] / "gcrm/ui/templates/person_detail.html").read_text()
    assert "curiosity-draft-button" in template
    assert "curiosity-language" in template
    assert "aria-busy" in template
