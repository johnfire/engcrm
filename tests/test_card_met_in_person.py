"""Scanned cards count as a contact only when the user says they met the person."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.routers.api_cards import MET_NOTE, ConfirmBody, complete_reviewed_capture

AUTH = {"Authorization": f"Bearer {create_token('admin')}"}
FIELDS = {"name": "Anna Roth", "company": "ACME"}


def _complete(met_in_person, person_id=7):
    body = ConfirmBody(fields=FIELDS, met_in_person=met_in_person)
    with patch("gcrm.api.routers.api_cards.save_reviewed_capture", return_value=({"image_path": None}, 3, person_id)), \
         patch("gcrm.api.routers.api_cards.log_audit"), \
         patch("gcrm.api.routers.api_cards.log_meeting_note") as org_note, \
         patch("gcrm.api.routers.api_cards.log_person_note") as person_note:
        result = complete_reviewed_capture(1, body, MagicMock())
    return result, org_note, person_note


def test_met_logs_contact_on_organization_and_person():
    result, org_note, person_note = _complete(True)
    org_note.assert_called_once_with(3, "in_person", MET_NOTE)
    person_note.assert_called_once_with(7, "visit", MET_NOTE)
    assert result["met_recorded"] is True


def test_not_met_logs_nothing():
    result, org_note, person_note = _complete(False)
    org_note.assert_not_called()
    person_note.assert_not_called()
    assert result["met_recorded"] is None


def test_card_without_person_logs_only_the_organization():
    _, org_note, person_note = _complete(True, person_id=0)
    org_note.assert_called_once()
    person_note.assert_not_called()


def test_log_failure_is_reported_not_raised():
    body = ConfirmBody(fields=FIELDS, met_in_person=True)
    with patch("gcrm.api.routers.api_cards.save_reviewed_capture", return_value=({"image_path": None}, 3, 7)), \
         patch("gcrm.api.routers.api_cards.log_audit"), \
         patch("gcrm.api.routers.api_cards.log_meeting_note", side_effect=RuntimeError("db down")):
        result = complete_reviewed_capture(1, body, MagicMock())
    assert result["met_recorded"] is False and result["contact_id"] == 3


def test_flag_defaults_to_false_for_older_clients():
    assert ConfirmBody(fields=FIELDS).met_in_person is False
