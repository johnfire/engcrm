"""Statistics against the real schema: activities and their minutes, sales and the
work behind each one, stage changes caught by the triggers, stuck organizations."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from gcrm.db.connection import db
from gcrm.tools.db_people import save_person
from gcrm.tools.statistics import add_sale, get_minute_defaults, get_statistics, set_minute_defaults

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 15)


def _workspace() -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def _organization(name: str, stage: str = "candidate") -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, city, pipeline_stage, status, workspace_id, created_at) "
            "VALUES (%s, 'Augsburg', %s, 'none', (SELECT id FROM workspaces WHERE slug = 'default'), "
            "'2026-09-01') RETURNING id",
            (name, stage),
        )
        return cursor.fetchone()["id"]


def _org_activity(contact_id: int, day: date, method: str | None, minutes=None, direction=None):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO interactions (contact_id, interaction_date, method, direction, outcome, summary, "
            "duration_minutes) VALUES (%s, %s, %s, %s, 'note', 'x', %s)",
            (contact_id, day, method, direction, minutes),
        )


def _person_activity(person_id: int, day: date, method: str | None, minutes=None):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO people_interactions (person_id, occurred_at, method, note, duration_minutes) "
            "VALUES (%s, %s, %s, 'x', %s)",
            (person_id, day, method, minutes),
        )


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    workspace = _workspace()
    acme = _organization("Acme GmbH", "suspect")
    quiet = _organization("Quiet AG", "prospect")
    anna = save_person("Anna Huber", contact_id=acme, allow_duplicate=True)
    d = date(2026, 10, 13)  # Monday of the period's week
    _org_activity(acme, date(2026, 9, 20), "in_person")             # first contact, before the period
    _org_activity(acme, d, "in_person")                              # drop-in 15
    _org_activity(acme, d, "meeting", minutes=60)                    # typed 60 beats the default 45
    _org_activity(acme, d, "email")                                  # 10
    _org_activity(acme, d, "email", direction="inbound")             # their reply: not work
    _org_activity(acme, d, None)                                     # plain note: 0
    _person_activity(anna, d + timedelta(days=1), "call")            # 15, counts towards Acme
    _person_activity(anna, d + timedelta(days=1), "video")           # 30
    _person_activity(anna, d + timedelta(days=1), "next_step")       # a plan, not work
    add_sale(workspace, acme, Decimal("1000"), date(2026, 9, 25), "Sketch")   # earlier sale
    add_sale(workspace, acme, Decimal("2400"), d + timedelta(days=2), "Painting")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE contacts SET pipeline_stage = 'prospect' WHERE id = %s", (acme,))
        cursor.execute("UPDATE contacts SET pipeline_stage = 'prospect' WHERE id = %s", (acme,))  # no change
        cursor.execute("UPDATE contacts SET pipeline_stage = 'not_in_pipeline' WHERE id = %s", (quiet,))
        cursor.execute("UPDATE contacts SET pipeline_stage = 'prospect' WHERE id = %s", (quiet,))
        cursor.execute("UPDATE stage_changes SET changed_at = '2026-10-14'")
    return {"workspace": workspace, "acme": acme, "quiet": quiet}


def test_effort_counts_types_and_minutes(world):
    stats = get_statistics(world["workspace"], date(2026, 10, 12), date(2026, 10, 18), today=TODAY)
    effort = stats["current"]["effort"]

    assert {k: (v["count"], v["minutes"]) for k, v in effort.items()} == {
        "drop_in": (1, 15), "meeting": (1, 60), "phone": (1, 15), "video": (1, 30),
        "email": (1, 10), "note": (1, 0),
    }
    assert stats["current"]["activities"] == 5 and stats["current"]["minutes"] == 130
    assert stats["current"]["estimated"] == 4  # all but the typed meeting used a default


def test_money_and_the_work_behind_each_sale(world):
    stats = get_statistics(world["workspace"], date(2026, 10, 12), date(2026, 10, 18), today=TODAY)

    assert stats["current"]["won_eur"] == Decimal("2400") and stats["current"]["sales"] == 1
    assert stats["current"]["eur_per_hour"] == Decimal("1107.69")  # 2400 / 130 min * 60
    (sale,) = stats["sales"]
    # since the previous sale on 25.9.: the 5 activities of the period's week, not the September drop-in
    assert (sale["organization"], sale["activities"], sale["minutes"]) == ("Acme GmbH", 5, 130)
    assert sale["previous_won"] == date(2026, 9, 25) and sale["weeks"] == 2.9  # 20 days


def test_stage_changes_are_recorded_by_the_database(world):
    stats = get_statistics(world["workspace"], date(2026, 10, 12), date(2026, 10, 18), today=TODAY)
    changes = {(c["from_stage"], c["to_stage"]): (c["n"], c["direction"]) for c in stats["current"]["stage_changes"]}

    assert changes == {
        ("suspect", "prospect"): (1, "forward"),
        ("prospect", "not_in_pipeline"): (1, "dropped"),
        ("not_in_pipeline", "prospect"): (1, "other"),
    }
    assert stats["current"]["promotions"] == 1


def test_a_working_organization_with_nothing_logged_for_weeks_is_stuck(world):
    stats = get_statistics(world["workspace"], date(2026, 10, 12), date(2026, 10, 18), today=TODAY)
    assert [s["name"] for s in stats["stuck"]] == ["Quiet AG"]


def test_the_previous_period_is_the_same_length_just_before(world):
    stats = get_statistics(world["workspace"], date(2026, 10, 12), date(2026, 10, 18), today=TODAY)
    assert (stats["previous_start"], stats["previous_end"]) == (date(2026, 10, 5), date(2026, 10, 11))
    assert stats["previous"]["activities"] == 0


def test_changed_default_minutes_apply_to_entries_without_a_typed_duration(world):
    set_minute_defaults(world["workspace"], {"drop_in": 20, "bogus": 99})
    assert get_minute_defaults(world["workspace"])["drop_in"] == 20

    stats = get_statistics(world["workspace"], date(2026, 10, 12), date(2026, 10, 18), today=TODAY)
    assert stats["current"]["effort"]["drop_in"]["minutes"] == 20
    assert stats["current"]["effort"]["meeting"]["minutes"] == 60  # typed, unchanged


def test_a_sale_needs_an_organization_of_the_workspace(world):
    assert add_sale(world["workspace"], 999999, Decimal("10"), TODAY, "") is None
    with pytest.raises(ValueError):
        add_sale(world["workspace"], world["acme"], Decimal("0"), TODAY, "")
