"""Field rules for merging a duplicate person — nothing the duplicate knows is lost."""
from datetime import date, datetime, timezone

from gcrm.tools.people_merge import plan_field_merge

TODAY = date(2026, 10, 5)


def _person(person_id: int, **fields) -> dict:
    base = {"id": person_id, "name": "Anna Huber", "workspace_id": 1, "notes": None,
            "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc)}
    return {**base, **fields}


def test_blank_fields_are_filled_from_the_duplicate():
    keep = _person(57, email=None, phone="", city="Augsburg")
    drop = _person(182, email="anna@example.test", phone="0821 1234", city="Augsburg")

    updates, conflicts = plan_field_merge(keep, drop, TODAY)

    assert updates == {"email": "anna@example.test", "phone": "0821 1234"}
    assert conflicts == []


def test_differing_values_keep_the_survivor_and_record_the_duplicates_in_notes():
    keep = _person(57, title="CEO", notes="Met at trade fair.")
    drop = _person(182, title="Managing Director")

    updates, conflicts = plan_field_merge(keep, drop, TODAY)

    assert "title" not in updates
    assert conflicts == ["title: Managing Director"]
    assert updates["notes"].startswith("Met at trade fair.\n\n[Merged from person #182 on 2026-10-05]")
    assert "title: Managing Director" in updates["notes"]


def test_values_that_differ_only_by_case_are_not_a_conflict():
    updates, conflicts = plan_field_merge(
        _person(57, email="Anna@Example.test"), _person(182, email="anna@example.test "), TODAY
    )
    assert updates == {} and conflicts == []


def test_both_notes_are_kept():
    updates, _ = plan_field_merge(_person(57, notes="First."), _person(182, notes="Second."), TODAY)
    assert updates["notes"] == "First.\n\n[Merged from person #182 on 2026-10-05]\nSecond."


def test_a_flag_set_on_either_person_stays_set():
    keep = _person(57, retention_hold=False, is_linkedin_contact=True)
    drop = _person(182, retention_hold=True, is_linkedin_contact=False)

    updates, _ = plan_field_merge(keep, drop, TODAY)

    assert updates == {"retention_hold": True}


def test_the_earlier_created_at_survives():
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updates, _ = plan_field_merge(_person(57), _person(182, created_at=earlier), TODAY)
    assert updates == {"created_at": earlier}


def test_row_bookkeeping_columns_are_never_copied():
    drop = _person(182, updated_at=datetime(2026, 10, 1, tzinfo=timezone.utc), workspace_id=1)
    updates, conflicts = plan_field_merge(_person(57, updated_at=None), drop, TODAY)
    assert updates == {} and conflicts == []
