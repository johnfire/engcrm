"""Mobile create/edit of organizations (POST/PATCH /api/contacts) and people
(POST/PATCH /api/people). DB mocked — no Postgres."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
VIEWER = {"Authorization": f"Bearer {create_token('viewer')}"}

ORG = "gcrm.api.routers.api_record_edit"
PEOPLE = "gcrm.api.routers.api_people"


def conn_returning(*rows):
    """A fake db() whose successive fetchone() calls return `rows`."""
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(rows)
    cursor.rowcount = 1
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def patch_db(module, *rows):
    conn, cursor = conn_returning(*rows)
    p = patch(f"{module}.db")
    mock_db = p.start()
    mock_db.return_value.__enter__.return_value = conn
    return p, cursor


class TestCreateOrganization:
    def post(self, body, existing=None, saved_id=77, headers=ADMIN):
        p, cursor = patch_db(ORG, *([existing] if existing else [None]) * 2)
        try:
            with patch(f"{ORG}.save_organization", return_value=saved_id) as save, \
                 patch(f"{ORG}.set_suppression_flag") as flag, \
                 patch(f"{ORG}._write_columns") as write:
                response = client.post("/api/contacts", json=body, headers=headers)
        finally:
            p.stop()
        return response, save, flag, write

    def test_creates_with_trimmed_fields(self):
        response, save, _, _ = self.post({"name": "  Acme GmbH ", "city": " Ulm ", "country": "de",
                                          "email": "a@acme.de", "notes": "met at fair"})
        assert response.status_code == 200 and response.json() == {"id": 77}
        args, kwargs = save.call_args
        assert args == ("Acme GmbH", "Ulm")
        assert kwargs["country"] == "DE" and kwargs["email"] == "a@acme.de" and kwargs["notes"] == "met at fair"

    def test_name_is_required(self):
        for body in ({}, {"name": ""}, {"name": "   "}, {"city": "Ulm"}):
            response, save, _, _ = self.post(body)
            assert response.status_code == 400, body
            save.assert_not_called()

    def test_viewer_cannot_create(self):
        response, save, _, _ = self.post({"name": "X"}, headers=VIEWER)
        assert response.status_code == 403
        save.assert_not_called()

    @pytest.mark.parametrize("body", [
        {"name": "x" * 201},
        {"name": "A", "country": "DEU"},
        {"name": "A", "country": "1x"},
        {"name": "A", "email": "not-an-email"},
        {"name": "A", "phone": "1" * 61},
        {"name": "A", "type": "t" * 61},
    ])
    def test_values_the_database_would_refuse_are_refused_with_a_message(self, body):
        response, save, _, _ = self.post(body)
        assert response.status_code == 400
        assert response.json()["detail"]
        save.assert_not_called()

    def test_an_existing_organization_is_reported_not_duplicated(self):
        response, save, _, _ = self.post(
            {"name": "Acme GmbH", "city": "Ulm"},
            existing={"id": 5, "name": "Acme GmbH", "city": "Ulm", "deleted_at": None})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["existing_id"] == 5 and detail["existing_name"] == "Acme GmbH"
        save.assert_not_called()

    def test_a_deleted_duplicate_is_reported_without_an_id_to_open(self):
        response, _, _, _ = self.post(
            {"name": "Acme GmbH", "city": "Ulm"},
            existing={"id": 5, "name": "Acme GmbH", "city": "Ulm", "deleted_at": "2026-01-01"})
        assert response.status_code == 409
        assert response.json()["detail"]["existing_id"] is None

    def test_an_ignored_chain_is_explained(self):
        response, _, _, _ = self.post({"name": "Starbucks", "city": "Ulm"}, saved_id=0)
        assert response.status_code == 409
        assert "ignored" in response.json()["detail"]["message"]

    def test_extra_fields_and_do_not_contact_are_applied_after_creation(self):
        response, _, flag, write = self.post(
            {"name": "A", "decision_maker": "Dr. Roth", "do_not_contact": True})
        assert response.status_code == 200
        write.assert_called_once_with(77, {"decision_maker": "Dr. Roth"}, None)
        flag.assert_called_once_with(77, "do_not_contact", True)


class TestEditOrganization:
    def patch_org(self, body, current=None, identity=(None, None), headers=ADMIN, coords=(48.4, 10.0)):
        current = {"city": "Ulm", "country": "DE", "name": "Acme"} if current is None else current
        p, cursor = patch_db(ORG, current or None)
        try:
            with patch(f"{ORG}._personal_identity", return_value=identity), \
                 patch(f"{ORG}._write_columns", return_value=True) as write, \
                 patch(f"{ORG}.set_suppression_flag") as flag, \
                 patch(f"{ORG}.geocode", return_value=coords) as geo, \
                 patch(f"{ORG}.log_audit"):
                response = client.patch("/api/contacts/9", json=body, headers=headers)
        finally:
            p.stop()
        return response, write, flag, geo

    def test_writes_only_the_fields_that_were_sent(self):
        response, write, _, geo = self.patch_org({"phone": " 0731 123 ", "notes": "call back"})
        assert response.status_code == 200
        assert write.call_args.args[1] == {"phone": "0731 123", "notes": "call back"}
        assert sorted(response.json()["changed"]) == ["notes", "phone"]
        geo.assert_not_called()

    def test_a_blank_value_clears_the_field_but_a_blank_name_is_refused(self):
        response, write, _, _ = self.patch_org({"website": "  "})
        assert response.status_code == 200 and write.call_args.args[1] == {"website": None}
        response, write, _, _ = self.patch_org({"name": " "})
        assert response.status_code == 400
        write.assert_not_called()

    def test_an_empty_request_is_refused(self):
        response, write, flag, _ = self.patch_org({})
        assert response.status_code == 400
        write.assert_not_called()
        flag.assert_not_called()

    def test_a_changed_city_replaces_the_coordinates(self):
        response, write, _, geo = self.patch_org({"city": "Augsburg"})
        assert response.status_code == 200
        geo.assert_called_once_with("Augsburg", "DE")
        written = write.call_args.args[1]
        assert (written["latitude"], written["longitude"]) == (48.4, 10.0)

    def test_a_city_that_cannot_be_located_clears_the_coordinates_rather_than_keeping_the_old_ones(self):
        _, write, _, _ = self.patch_org({"city": "Nowhereville"}, coords=None)
        written = write.call_args.args[1]
        assert written["latitude"] is None and written["longitude"] is None

    def test_the_same_city_again_does_not_touch_the_coordinates(self):
        _, write, _, geo = self.patch_org({"city": " Ulm "})
        geo.assert_not_called()
        assert "latitude" not in write.call_args.args[1]

    def test_do_not_contact_goes_through_the_suppression_helper(self):
        response, write, flag, _ = self.patch_org({"do_not_contact": True})
        assert response.status_code == 200
        flag.assert_called_once_with(9, "do_not_contact", True)
        write.assert_not_called()

    def test_unknown_organization_is_404(self):
        response, _, _, _ = self.patch_org({"phone": "1"}, current={})
        assert response.status_code == 404

    def test_viewer_cannot_edit(self):
        response, write, _, _ = self.patch_org({"phone": "1"}, headers=VIEWER)
        assert response.status_code == 403
        write.assert_not_called()

    def test_the_workspace_scope_is_applied_for_a_real_account(self):
        _, write, _, _ = self.patch_org({"phone": "1"}, identity=(3, 12))
        assert write.call_args.args[2] == 12


class TestPeople:
    def create(self, body, existing_id=None, org_found=True, saved_id=31, headers=ADMIN):
        with patch(f"{PEOPLE}._personal_identity", return_value=(None, None)), \
             patch(f"{PEOPLE}._organization_exists", return_value=org_found), \
             patch(f"{PEOPLE}.db"), \
             patch(f"{PEOPLE}.find_existing_person", return_value=existing_id), \
             patch(f"{PEOPLE}.save_person", return_value=saved_id) as save, \
             patch(f"{PEOPLE}.update_person") as update, \
             patch(f"{PEOPLE}.log_audit"):
            response = client.post("/api/people", json=body, headers=headers)
        return response, save, update

    def test_creates_a_person_at_an_organization(self):
        response, save, _ = self.create({"name": " Anna Roth ", "title": "CTO", "contact_id": 4, "country": "at"})
        assert response.status_code == 200 and response.json() == {"id": 31}
        args, kwargs = save.call_args
        assert args == ("Anna Roth",)
        assert kwargs["title"] == "CTO" and kwargs["contact_id"] == 4
        assert kwargs["country"] == "AT" and kwargs["source"] == "manual"

    def test_name_is_required_and_viewer_is_refused(self):
        response, save, _ = self.create({"title": "CTO"})
        assert response.status_code == 400
        response, save, _ = self.create({"name": "A"}, headers=VIEWER)
        assert response.status_code == 403
        save.assert_not_called()

    def test_an_existing_person_is_reported_with_their_id(self):
        response, save, _ = self.create({"name": "Anna Roth"}, existing_id=8)
        assert response.status_code == 409
        assert response.json()["detail"]["existing_id"] == 8
        save.assert_not_called()

    def test_an_unknown_organization_is_refused(self):
        response, save, _ = self.create({"name": "A", "contact_id": 999}, org_found=False)
        assert response.status_code == 404
        save.assert_not_called()

    def test_a_linkedin_url_must_be_a_linkedin_link(self):
        response, save, _ = self.create({"name": "A", "linkedin_url": "https://example.com/x"})
        assert response.status_code == 400
        save.assert_not_called()
        response, save, update = self.create({"name": "A", "linkedin_url": "https://www.linkedin.com/in/anna-roth/"})
        assert response.status_code == 200
        update.assert_called_once()

    def edit(self, body, updated=True, headers=ADMIN, raises=None):
        with patch(f"{PEOPLE}.update_person", return_value=updated, side_effect=raises) as update, \
             patch(f"{PEOPLE}.log_audit"):
            response = client.patch("/api/people/6", json=body, headers=headers)
        return response, update

    def test_edit_sends_only_what_changed_and_clears_blank_fields(self):
        response, update = self.edit({"phone": " 123 ", "notes": ""})
        assert response.status_code == 200
        update.assert_called_once_with(6, {"phone": "123", "notes": ""})

    def test_edit_refusals(self):
        assert self.edit({})[0].status_code == 400
        assert self.edit({"name": " "})[0].status_code == 400
        assert self.edit({"contact_id": 3})[0].status_code == 400
        assert self.edit({"phone": "1"}, headers=VIEWER)[0].status_code == 403
        assert self.edit({"phone": "1"}, updated=False)[0].status_code == 404
        assert self.edit({"phone": "1"}, raises=ValueError("x"))[0].status_code == 400
