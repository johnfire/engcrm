"""A deal's follow-ups only accumulate. No next step, whether from the deal card, the phone or an old
phone build, rewrites another follow-up, and the deal's next step is the earliest active one."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_offers import list_offers
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_users import create_user
from gcrm.tools.deal_records import add_deal, get_deals, set_deal_next_step
from gcrm.tools.follow_ups import change_follow_up_status, create_follow_up, list_follow_ups

pytestmark = pytest.mark.integration

PHONE = {"Authorization": f"Bearer {create_token('admin')}"}
EARLY, LATE = date(2026, 12, 4), date(2026, 12, 11)


@pytest.fixture
def deal(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    organization = save_organization("Beispiel Werke GmbH", "Friedrichshafen", source="test_fixture")
    return get_deals("organization", organization)[0]


@pytest.fixture
def web(deal):
    """The website, signed in as an admin (the Follow-ups page shows its actions to admins only)."""
    password = "add-only-testing-password"
    create_user("add-only@example.test", hash_password(password), "admin")
    client = TestClient(app)
    signed_in = client.post("/login", data={"email": "add-only@example.test", "password": password},
                            follow_redirects=False)
    assert signed_in.status_code == 303
    return client


def _tasks() -> list[tuple]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT task_text, status, task_type, due_date FROM follow_ups ORDER BY id")
        return [tuple(row.values()) for row in cursor.fetchall()]


def _next(deal: dict) -> tuple:
    current = next(d for d in get_deals("organization", deal["contact_id"]) if d["id"] == deal["id"])
    return current["next_step"], current["next_step_date"]


def _promise(deal: dict, text: str = "Meet in Friedrichshafen", due: date | None = EARLY,
             task_type: str | None = "commitment") -> None:
    """A follow-up promised while logging an activity about the deal's offer."""
    log_meeting_note(deal["contact_id"], "phone", "Spoke", follow_up_date=due, follow_up_text=text,
                     follow_up_type=task_type, offer_id=deal["offer_id"])


def _phone_step(deal: dict, text: str | None, due: date | None = None, task_type: str | None = None):
    body = {"next_step": text, "next_step_date": due.isoformat() if due else None,
            **({"task_type": task_type} if task_type else {})}
    response = TestClient(app).put(f"/api/deals/{deal['id']}/next-step", headers=PHONE, json=body)
    assert response.status_code == 200, response.text
    return response.json()


PROMISE = ("Meet in Friedrichshafen", "active", "commitment", EARLY)


# --- the next step follows the follow-ups -----------------------------------------

def test_a_typed_activity_promise_is_the_deals_next_step_at_once(deal):
    _promise(deal)
    assert _next(deal) == ("Meet in Friedrichshafen", "2026-12-04")


def test_a_promise_without_a_type_does_not_replace_the_step_shown(deal):
    set_deal_next_step(deal["id"], "Call", None)
    _promise(deal, "Send brochure", task_type=None)
    assert _next(deal) == ("Call", None)


# --- adding never rewrites ---------------------------------------------------------

@pytest.mark.parametrize("task_type, status", [("check_in", "active"), (None, "review")])
def test_a_new_step_from_the_phone_is_added_beside_the_promise(deal, task_type, status):
    _promise(deal)
    answered = _phone_step(deal, "Send quote", LATE, task_type)
    assert _tasks() == [PROMISE, ("Send quote", status, task_type, LATE)]
    assert (answered["next_step"], answered["next_step_date"]) == ("Meet in Friedrichshafen", "2026-12-04")


@pytest.mark.parametrize("task_type", ["check_in", None])
def test_saving_a_step_that_is_already_there_adds_nothing(deal, task_type):
    _promise(deal)
    _phone_step(deal, "Send quote", LATE, task_type)
    before = _tasks()
    assert _phone_step(deal, " Send quote ", LATE, task_type)["logged"] is False   # a retry
    assert _tasks() == before


def test_saving_an_active_step_with_another_type_leaves_it_as_it_is(deal):
    _promise(deal)
    assert _phone_step(deal, "Meet in Friedrichshafen", EARLY, "check_in")["logged"] is False
    assert _tasks() == [PROMISE]


def test_the_same_words_on_another_day_are_a_new_follow_up(deal):
    _promise(deal)
    _phone_step(deal, "Meet in Friedrichshafen", LATE, "commitment")
    assert _tasks() == [PROMISE, ("Meet in Friedrichshafen", "active", "commitment", LATE)]


def test_steps_without_a_type_no_longer_replace_each_other(deal):
    _phone_step(deal, "Call")
    _phone_step(deal, "Write")
    assert _tasks() == [("Call", "review", None, None), ("Write", "review", None, None)]
    assert _next(deal) == ("Write", None)


def test_a_waiting_step_saved_with_a_type_is_activated_with_its_new_day(deal):
    _phone_step(deal, "Call", EARLY)
    _phone_step(deal, "Call", LATE, "check_in")
    assert _tasks() == [("Call", "active", "check_in", LATE)]


# --- done ---------------------------------------------------------------------------

def test_done_from_an_old_phone_completes_only_the_earliest(deal):
    _promise(deal)
    _phone_step(deal, "Send quote", LATE, "check_in")
    _phone_step(deal, None)
    assert [row[:2] for row in _tasks()] == [("Meet in Friedrichshafen", "completed"), ("Send quote", "active")]
    assert _next(deal) == ("Send quote", "2026-12-11")
    _phone_step(deal, None)
    assert _next(deal) == (None, None)


def test_done_with_only_waiting_steps_completes_the_one_shown(deal):
    _phone_step(deal, "Call")
    _phone_step(deal, "Write")
    _phone_step(deal, None)
    assert [row[:2] for row in _tasks()] == [("Call", "review"), ("Write", "completed")]
    assert _next(deal) == (None, None)


def test_clearing_a_step_that_has_no_follow_up_behind_it_still_clears_the_deal(deal):
    with db() as connection:
        connection.cursor().execute("UPDATE deals SET next_step = 'Old plan' WHERE id = %s", (deal["id"],))
    assert _phone_step(deal, None)["logged"] is True
    assert _next(deal) == (None, None) and _tasks() == []


# --- the web deal card ---------------------------------------------------------------

def _card(web: TestClient, deal: dict) -> str:
    page = web.get(f"/organizations/{deal['contact_id']}?lang=en").text
    return re.search(rf'<article class="deal-card" id="deal-{deal["id"]}">(.*?)</article>', page, re.S).group(1)


def test_the_card_lists_every_active_follow_up_of_its_deal(deal, web):
    _promise(deal, due=date(2020, 1, 31))
    create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Ask about the budget", due_date=LATE)
    for status in ("completed", "dismissed"):
        task_id = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text=f"Was {status}")
        version = next(t for t in list_follow_ups() if t["id"] == task_id)["updated_at"]
        change_follow_up_status(task_id, status, version)
    set_deal_next_step(deal["id"], "Waiting for a type", None)
    offer = next(o for o in list_offers(None) if o["slug"] == "learnwohl")
    other = add_deal("organization", deal["contact_id"], offer["id"])
    create_follow_up(deal_id=other, task_type="check_in", task_text="Another offer's step")

    card = _card(web, deal)
    assert card.index("Meet in Friedrichshafen") < card.index("Ask about the budget")
    assert "31.01.2020" in card and "11.12.2026" in card
    assert "Commitment" in card and "Check-in" in card
    assert card.count("next-step__due--overdue") == 1 and "Overdue" in card
    for hidden in ("Was completed", "Was dismissed", "Waiting for a type", "Another offer&#39;s step"):
        assert hidden not in card
    for task in (t for t in list_follow_ups() if t["deal_id"] == deal["id"]):
        assert f'action="/follow-ups/{task["id"]}/status"' in card
        assert f'name="version" value="{task["updated_at"].isoformat()}"' in card
        assert f'href="/follow-ups/?task={task["id"]}"' in card
    # one form only adds; nothing on the card edits an existing follow-up
    assert "/next-step" not in card and "/edit" not in card
    add = card[card.index('action="/follow-ups/new"'):]
    add = add[:add.index("</form>")]
    assert f'name="target" value="deal:{deal["id"]}"' in add
    assert re.search(r'<select name="task_type"[^>]*required', add) and "value=\"Meet" not in add


def test_done_on_the_card_completes_that_follow_up_only_and_returns(deal, web):
    _promise(deal)
    second = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Ask", due_date=LATE)
    version = next(t for t in list_follow_ups() if t["id"] == second)["updated_at"].isoformat()
    page = f"/organizations/{deal['contact_id']}"
    form = {"status": "completed", "version": version, "next": page}
    done = web.post(f"/follow-ups/{second}/status", data=form, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"] == page
    assert [row[:2] for row in _tasks()] == [("Meet in Friedrichshafen", "active"), ("Ask", "completed")]
    assert _next(deal) == ("Meet in Friedrichshafen", "2026-12-04")
    assert web.post(f"/follow-ups/{second}/status", data=form, follow_redirects=False).status_code == 409


def test_add_on_the_card_creates_a_follow_up_and_returns(deal, web):
    _promise(deal, due=LATE)
    page = f"/organizations/{deal['contact_id']}"
    form = {"target": f"deal:{deal['id']}", "task_text": "Send quote", "due_date": "04.12.2026", "next": page}
    refused = web.post("/follow-ups/new", data={**form, "task_type": "someday"}, follow_redirects=False)
    assert refused.status_code == 400 and len(_tasks()) == 1
    added = web.post("/follow-ups/new", data={**form, "task_type": "check_in"}, follow_redirects=False)
    assert added.status_code == 303 and added.headers["location"] == page
    assert _tasks() == [("Meet in Friedrichshafen", "active", "commitment", LATE),
                        ("Send quote", "active", "check_in", EARLY)]
    assert _next(deal) == ("Send quote", "2026-12-04")
    away = web.post("/follow-ups/new", data={**form, "task_type": "check_in", "next": "https://evil.test/"},
                    follow_redirects=False)
    assert away.headers["location"] == "/follow-ups/"


def test_the_cards_edit_link_opens_that_one_follow_up(deal, web):
    _promise(deal)
    second = create_follow_up(deal_id=deal["id"], task_type="check_in", task_text="Ask about the budget")
    page = web.get(f"/follow-ups/?task={second}&lang=en").text
    table = page[page.index("<tbody>"):page.index("</tbody>")]
    assert "Ask about the budget" in table and "Meet in Friedrichshafen" not in table
    assert re.search(rf'<details open>.*?action="/follow-ups/{second}/edit"', table, re.S)
