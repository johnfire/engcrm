"""Migration 114 on real Postgres: a deal whose next step fell behind its active follow-ups shows the
earliest one again. Every other deal keeps what it has, nothing else is written, and running the
migration again changes nothing."""
from datetime import date
from pathlib import Path

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.deal_records import get_deals, set_deal_next_step
from gcrm.tools.follow_ups import create_follow_up

pytestmark = pytest.mark.integration

MIGRATION = Path(__file__).parents[2] / "gcrm" / "db" / "migrations" / "114_reproject_deal_next_steps.sql"
EARLY, LATE = date(2026, 12, 4), date(2026, 12, 20)


def _rows(sql: str, *values) -> list[dict]:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, values)
        return [dict(row) for row in cursor.fetchall()]


def _show(deal_id: int, text: str, due: date | None, removed: bool = False) -> None:
    """Make a deal show something other than its follow-ups say, as production could."""
    with db() as connection:
        connection.cursor().execute(
            "UPDATE deals SET next_step=%s, next_step_date=%s, deleted_at=CASE WHEN %s THEN NOW() END WHERE id=%s",
            (text, due, removed, deal_id))


@pytest.fixture
def deals(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    found = {}
    for name in ("stale", "quiet", "correct", "removed"):
        organization = save_organization(f"Beispiel {name} GmbH", "Augsburg", source="test_fixture")
        found[name] = get_deals("organization", organization)[0]

    # behind an older activity promise: the card's later step is what the deal shows
    stale = found["stale"]
    log_meeting_note(stale["contact_id"], "phone", "Spoke", follow_up_date=EARLY,
                     follow_up_text="Meet in Friedrichshafen", follow_up_type="commitment", offer_id=stale["offer_id"])
    create_follow_up(deal_id=stale["id"], task_type="check_in", task_text="Call back", due_date=LATE)
    create_follow_up(deal_id=stale["id"], task_type="check_in", task_text="Some day")
    _show(stale["id"], "Call back", LATE)
    # nothing active: only a step waiting for review, whose text must stay
    set_deal_next_step(found["quiet"]["id"], "Old plan", EARLY)
    # already right
    create_follow_up(deal_id=found["correct"]["id"], task_type="check_in", task_text="Send quote", due_date=EARLY)
    # a removed deal is left alone
    create_follow_up(deal_id=found["removed"]["id"], task_type="check_in", task_text="Active", due_date=EARLY)
    _show(found["removed"]["id"], "Gone", LATE, removed=True)
    return {name: deal["id"] for name, deal in found.items()}


def _state() -> dict:
    return {
        "deals": {row.pop("id"): row for row in
                  _rows("SELECT id, next_step, next_step_date, updated_at, pipeline_stage, status FROM deals")},
        "follow_ups": _rows("SELECT * FROM follow_ups ORDER BY id"),
        "history": _rows("SELECT id FROM interactions ORDER BY id"),
        "changes": _rows("SELECT count(*) AS n FROM sync_entity_changes")[0]["n"],
    }


def _migrate() -> None:
    with db() as connection:
        connection.cursor().execute(MIGRATION.read_text())


def test_only_the_stale_deal_is_corrected_and_a_second_run_changes_nothing(deals):
    before = _state()
    _migrate()
    after = _state()

    fixed = after["deals"][deals["stale"]]
    assert (fixed["next_step"], fixed["next_step_date"]) == ("Meet in Friedrichshafen", EARLY)
    for name in ("quiet", "correct", "removed"):
        assert after["deals"][deals[name]] == before["deals"][deals[name]], name
    assert after["deals"][deals["quiet"]]["next_step"] == "Old plan"
    assert after["follow_ups"] == before["follow_ups"] and after["history"] == before["history"]
    assert after["changes"] == before["changes"] + 1          # the phone is told about the one deal

    _migrate()
    assert _state() == after
    assert _rows("SELECT reproject_deal_next_steps() AS changed") == [{"changed": 0}]


def test_the_corrected_step_is_clocked_so_an_older_phone_edit_cannot_undo_it(deals):
    """Offline sync lets the newer field clock win, so the correction must carry the migration's time."""
    (started,) = _rows("SELECT clock_timestamp() AS now")
    _migrate()
    clocks = _rows("SELECT v.field_name, v.changed_at > %s AS newer FROM sync_field_versions v "
                   "JOIN deals d ON d.sync_id = v.entity_sync_id WHERE d.id = %s "
                   "AND v.field_name IN ('next_step', 'next_step_date') ORDER BY v.field_name",
                   started["now"], deals["stale"])
    assert clocks == [{"field_name": "next_step", "newer": True}, {"field_name": "next_step_date", "newer": True}]
