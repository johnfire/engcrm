"""Log activity absorbed Visit Info: each logged activity carries its date,
impression, materials left and follow-up, and the organization's visit summary
is read back from those activities."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gcrm.activity_types import IMPRESSIONS, parse_impression, parse_occurred_on
from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.routers import organizations, statistics
from gcrm.supervisor import run_interview
from gcrm.tools import db_interactions

ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
TODAY = date(2026, 10, 30)


# --- parsing -------------------------------------------------------------------

def test_activity_date_is_today_or_earlier():
    assert parse_occurred_on("", TODAY) is None  # blank: logged as today
    assert parse_occurred_on("2026-10-29", TODAY) == date(2026, 10, 29)
    assert parse_occurred_on("2026-10-30", TODAY) == TODAY
    with pytest.raises(ValueError):
        parse_occurred_on("2026-10-31", TODAY)
    with pytest.raises(ValueError):
        parse_occurred_on("yesterday", TODAY)


def test_impression_is_one_of_four_or_blank():
    assert IMPRESSIONS == ("warm", "neutral", "cold", "skeptical")
    assert parse_impression(" warm ") == "warm"
    assert parse_impression("") is None
    with pytest.raises(ValueError):
        parse_impression("lukewarm")


# --- web form -----------------------------------------------------------------

def _web_log(**fields):
    form = {"method": "in_person", "duration_minutes": "", "note": "Met Anna", "offer": None,
            "occurred_on": "", "impression": "", "materials_left": "", "followup_promised": "",
            "followup_date": ""}
    form.update(fields)
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {"?column?": 1}
    with patch.object(statistics, "db") as database, \
         patch.object(statistics, "_workspace_id", return_value=1), \
         patch.object(statistics, "resolve_log_offer", return_value=None), \
         patch.object(statistics, "log_meeting_note") as log:
        database.return_value.__enter__.return_value = connection
        statistics.log_activity(SimpleNamespace(session={}), 7, _admin="admin", **form)
    return log


def test_web_form_logs_the_whole_visit_as_one_activity():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    log = _web_log(occurred_on=yesterday, duration_minutes="25", impression="warm",
                   materials_left=" flyer, price list ", followup_promised=" send quote ",
                   followup_date="2026-11-15")
    log.assert_called_once_with(
        7, "in_person", "Met Anna", follow_up_date=date(2026, 11, 15), follow_up_text="send quote",
        duration_minutes=25, offer_id=None, occurred_on=date.fromisoformat(yesterday), impression="warm",
        materials_left="flyer, price list",
    )


def test_web_form_with_only_the_basics_stores_blanks_as_none():
    log = _web_log()
    kwargs = log.call_args.kwargs
    assert kwargs["occurred_on"] is None and kwargs["impression"] is None
    assert kwargs["materials_left"] is None and kwargs["follow_up_text"] is None


@pytest.mark.parametrize("fields", [
    {"occurred_on": (date.today() + timedelta(days=1)).isoformat()},
    {"impression": "ecstatic"},
    {"followup_date": "next week"},
])
def test_web_form_refuses_bad_visit_details(fields):
    with pytest.raises(HTTPException) as error:
        _web_log(**fields)
    assert error.value.status_code == 400


# --- mobile API ---------------------------------------------------------------

def test_mobile_note_carries_the_visit_details():
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {"?column?": 1}
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with patch("gcrm.api.routers.api_organizations.db") as database, \
         patch("gcrm.api.routers.api_organizations.log_meeting_note", return_value=3) as log:
        database.return_value.__enter__.return_value = connection
        response = TestClient(app).post("/api/contacts/7/notes", headers=ADMIN, json={
            "note": "Visit", "method": "in_person", "occurred_on": yesterday,
            "impression": "cold", "materials_left": " card "})
    assert response.status_code == 200
    kwargs = log.call_args.kwargs
    assert kwargs["occurred_on"] == date.fromisoformat(yesterday)
    assert kwargs["impression"] == "cold" and kwargs["materials_left"] == "card"


@pytest.mark.parametrize("body", [
    {"occurred_on": (date.today() + timedelta(days=1)).isoformat()},
    {"impression": "great"},
])
def test_mobile_note_refuses_bad_visit_details(body):
    with patch("gcrm.api.routers.api_organizations.log_meeting_note") as log:
        response = TestClient(app).post("/api/contacts/7/notes", headers=ADMIN, json={"note": "Visit", **body})
    assert response.status_code == 400
    log.assert_not_called()


# --- edit form no longer touches Visit Info -------------------------------------

def test_editing_an_organization_leaves_the_old_visit_columns_alone():
    with patch.object(organizations, "_persist_organization_edit") as persist, \
         patch.object(organizations, "log_audit"):
        organizations.organization_edit(
            7, SimpleNamespace(session={}), name="Acme", city="", country="", type="",
            do_not_organization=False, email_bounced=False, research_exhausted=False, fit_score=None,
            email="", phone="", website="", preferred_contact_method="", decision_maker="",
            best_visit_time="Tue mornings", access_notes="", space_notes="", price_sensitivity="",
            notes="", _admin="admin",
        )
    written = persist.call_args.args[1]
    assert written["best_visit_time"] == "Tue mornings"
    for gone in ("last_visited_at", "visit_duration", "first_impression", "last_impression",
                 "materials_left", "followup_promised"):
        assert gone not in written


# --- summary and the interview command ------------------------------------------

def test_visit_summary_skips_deal_next_steps_and_counts_only_in_person_as_visits():
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {"last_visited": None}
    with patch.object(db_interactions, "db") as database:
        database.return_value.__enter__.return_value = connection
        db_interactions.get_visit_summary(7)
    sql, params = connection.cursor.return_value.execute.call_args.args
    assert "method IN ('in_person', 'meeting')" in sql
    assert "IS DISTINCT FROM 'next_step'" in sql and "IS DISTINCT FROM 'next_step_done'" in sql
    assert params == {"id": 7}


def test_interview_logs_the_visit_as_an_in_person_activity():
    with patch.object(run_interview, "log_meeting_note") as log:
        run_interview.log_visit(7, {"occurred_on": "2026-10-28", "impression": "warm",
                                    "materials_left": "flyer", "follow_up_text": "call in May"}, "Saw the owner")
    log.assert_called_once_with(7, "in_person", "Saw the owner", follow_up_text="call in May",
                                occurred_on=date(2026, 10, 28), impression="warm", materials_left="flyer")
