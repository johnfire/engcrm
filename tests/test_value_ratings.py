"""Short- and long-term value ratings: private per user, 0 (zero) to 3 (high),
set and cleared one at a time on organizations and people."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.auth import require_login
from gcrm.api.main import app
from gcrm.api.routers import api_organizations, api_people, organizations, people
from gcrm.api.templates import templates
from gcrm.i18n import translate
from gcrm.tools import db_people, db_personal_priorities
from gcrm.tools.db_personal_ratings import check_rating, store_rating


def _mock_database(*fetchone_values):
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(fetchone_values)
    connection = MagicMock()
    connection.cursor.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return context, cursor


# --- storage -----------------------------------------------------------------

def test_setting_a_value_upserts_only_that_column():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"short_term_value": 3}

    stored = store_rating(cursor, "contact_user_priorities", 7, 3, 42, "short_term_value", 3)

    sql, params = cursor.execute.call_args.args
    assert stored == 3
    assert "INSERT INTO contact_user_priorities (workspace_id, user_id, contact_id, short_term_value)" in sql
    assert "ON CONFLICT (user_id, contact_id)" in sql
    assert "short_term_value = EXCLUDED.short_term_value" in sql
    assert "priority = EXCLUDED" not in sql
    assert params == (3, 7, 42, 3)


def test_zero_is_a_rating_not_a_clear():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"long_term_value": 0}

    assert store_rating(cursor, "person_user_priorities", 7, 3, 42, "long_term_value", 0) == 0
    assert "INSERT INTO person_user_priorities" in cursor.execute.call_args.args[0]


def test_clearing_a_value_keeps_the_users_other_ratings():
    cursor = MagicMock()

    assert store_rating(cursor, "contact_user_priorities", 7, 3, 42, "long_term_value", None) is None

    delete_sql, delete_params = cursor.execute.call_args_list[0].args
    update_sql, update_params = cursor.execute.call_args_list[1].args
    # The row goes only when nothing else is rated on it ...
    assert delete_sql.startswith("DELETE FROM contact_user_priorities")
    assert "priority IS NULL AND short_term_value IS NULL" in delete_sql
    assert "long_term_value IS NULL" not in delete_sql
    # ... otherwise just this one column is blanked.
    assert "SET long_term_value = NULL" in update_sql
    assert delete_params == update_params == (7, 3, 42)


def test_clearing_priority_no_longer_wipes_the_value_ratings():
    cursor = MagicMock()

    store_rating(cursor, "contact_user_priorities", 7, 3, 42, "priority", None)

    delete_sql = cursor.execute.call_args_list[0].args[0]
    assert "short_term_value IS NULL AND long_term_value IS NULL" in delete_sql
    assert "SET priority = NULL" in cursor.execute.call_args_list[1].args[0]


@pytest.mark.parametrize("value", [-1, 4])
def test_values_outside_zero_to_three_are_rejected(value):
    with pytest.raises(ValueError, match="between 0 and 3"):
        check_rating("short_term_value", value)


def test_unknown_rating_names_never_reach_sql():
    cursor = MagicMock()
    with pytest.raises(ValueError, match="Unknown rating"):
        store_rating(cursor, "contact_user_priorities", 7, 3, 42, "priority; DROP TABLE x", 1)
    cursor.execute.assert_not_called()


def test_organization_value_is_hidden_across_workspaces():
    context, cursor = _mock_database(None)
    with patch.object(db_personal_priorities, "db", return_value=context):
        stored = db_personal_priorities.set_organization_rating(7, 3, 42, "short_term_value", 2)

    assert stored == (False, None)
    assert cursor.execute.call_count == 1


def test_person_value_is_stored_on_the_person_ratings_row():
    context, cursor = _mock_database({"exists": 1}, {"long_term_value": 1})
    with patch.object(db_people, "db", return_value=context):
        stored = db_people.set_person_rating(7, 3, 42, "long_term_value", 1)

    assert stored == (True, 1)
    assert "ON CONFLICT (user_id, person_id)" in cursor.execute.call_args_list[1].args[0]


# --- routes ------------------------------------------------------------------

def test_web_organization_route_sets_the_horizon_and_audits():
    request = SimpleNamespace(session={"user_id": 7, "workspace_id": 3})
    with (
        patch.object(organizations, "set_organization_rating", return_value=(True, 3)) as save,
        patch.object(organizations, "log_audit") as log_audit,
    ):
        response = organizations.update_value_rating(
            42, "short-term", organizations.ValueRatingBody(value=3), request,
        )

    assert response == {"short_term_value": 3}
    save.assert_called_once_with(7, 3, 42, "short_term_value", 3)
    assert log_audit.call_args.args[2:] == ("contact.short_term_value_changed", "contact:42", "set:3")


def test_web_person_route_clears_the_long_term_value():
    request = SimpleNamespace(session={"user_id": 7, "workspace_id": 3})
    with (
        patch.object(people, "set_person_rating", return_value=(True, None)) as save,
        patch.object(people, "log_audit") as log_audit,
    ):
        response = people.update_person_value(42, "long-term", people.ValueBody(value=None), request)

    assert response == {"long_term_value": None}
    save.assert_called_once_with(7, 3, 42, "long_term_value", None)
    assert log_audit.call_args.args[2:] == ("person.long_term_value_changed", "person:42", "cleared")


@pytest.mark.parametrize(
    ("horizon", "value", "session", "status"),
    [
        ("mid-term", 1, {"user_id": 7, "workspace_id": 3}, 404),
        ("short-term", 4, {"user_id": 7, "workspace_id": 3}, 400),
        ("short-term", 1, {"user_id": None, "workspace_id": None}, 403),
    ],
)
def test_web_organization_route_refuses_bad_requests(horizon, value, session, status):
    request = SimpleNamespace(session=session)
    with patch.object(organizations, "set_organization_rating") as save:
        with pytest.raises(organizations.HTTPException) as error:
            organizations.update_value_rating(42, horizon, organizations.ValueRatingBody(value=value), request)

    assert error.value.status_code == status
    save.assert_not_called()


def test_mobile_api_routes_set_values_for_the_tokens_account():
    with (
        patch.object(api_organizations, "_personal_identity", return_value=(7, 3)),
        patch.object(api_organizations, "set_organization_rating", return_value=(True, 2)) as save_org,
        patch.object(api_organizations, "log_audit"),
        patch.object(api_people, "_personal_identity", return_value=(7, 3)),
        patch.object(api_people, "set_person_rating", return_value=(True, 0)) as save_person,
        patch.object(api_people, "log_audit"),
    ):
        org = api_organizations.update_value_rating(
            42, "long-term", api_organizations.ValueRatingBody(value=2), payload={},
        )
        person = api_people.set_value(9, "short-term", api_people.ValueBody(value=0), payload={})

    assert org == {"long_term_value": 2}
    assert person == {"short_term_value": 0}
    save_org.assert_called_once_with(7, 3, 42, "long_term_value", 2)
    save_person.assert_called_once_with(7, 3, 9, "short_term_value", 0)


def test_mobile_api_shared_admin_has_no_value_ratings():
    with patch.object(api_people, "_personal_identity", return_value=(None, None)):
        with pytest.raises(api_people.HTTPException) as error:
            api_people.set_value(9, "short-term", api_people.ValueBody(value=1), payload={})

    assert error.value.status_code == 403


def test_values_are_sortable_on_both_lists():
    assert organizations.SORT_COLUMNS["short_term_value"] == "cup.short_term_value"
    assert api_organizations.SORT_COLUMNS["long_term_value"] == "cup.long_term_value"
    assert db_people.SORT_COLUMNS["long_term_value"] == "person_priority.long_term_value"


# --- template ----------------------------------------------------------------

def test_value_panel_marks_each_horizon_separately_and_zero_counts():
    rendered = templates.env.get_template("partials/value_ratings.html").render(
        record={"short_term_value": 0, "long_term_value": None},
        rating_url="/organizations/42",
        request=SimpleNamespace(session={"user_id": 7}),
        t=lambda key: translate(key, "en"),
    )

    assert 'data-url="/organizations/42/value/short-term"' in rendered
    assert 'data-url="/organizations/42/value/long-term"' in rendered
    assert "Short-term value" in rendered and "Long-term value" in rendered
    assert all(level in rendered for level in ("High", "Medium", "Low", "Zero"))
    # Zero on short-term is selected; long-term is unrated, so its clear button is disabled.
    markup = rendered.split("<script>")[0]
    assert markup.count('aria-pressed="true"') == 1
    assert 'class="personal-priority__button tone-gray selected"\n        data-rating-value="0"' in markup
    assert markup.count("disabled") == 1


def test_value_panel_asks_shared_admin_to_sign_in():
    rendered = templates.env.get_template("partials/value_ratings.html").render(
        record={"short_term_value": None, "long_term_value": None},
        rating_url="/people/9",
        request=SimpleNamespace(session={}),
        t=lambda key: translate(key, "en"),
    )

    assert "Sign in with a personal account" in rendered
    assert "data-value-rating" not in rendered.split("<script>")[0]


# --- colours and priority 6 ----------------------------------------------------

def test_each_rating_level_has_the_requested_colour():
    priority_tone = templates.env.globals["priority_tone"]
    value_tone = templates.env.globals["value_tone"]
    assert priority_tone == {1: "green", 2: "yellow", 3: "blue", 4: "orange", 5: "gray", 6: "dark"}
    assert value_tone == {3: "green", 2: "yellow", 1: "blue", 0: "gray"}
    css = (Path(__file__).parents[1] / "gcrm/ui/static/style.css").read_text()
    for tone in {*priority_tone.values(), *value_tone.values()}:
        assert f".tone-{tone} " in css
    assert "--on-tone: #ffffff" in css.split(".tone-dark")[1].split("}")[0]  # white lettering


def test_priority_panel_offers_forget_it_and_colours_every_button():
    rendered = templates.env.get_template("partials/personal_priority.html").render(
        organization={"id": 42, "personal_priority": 6},
        request=SimpleNamespace(session={"user_id": 7}),
        t=lambda key: translate(key, "en"),
    )
    markup = rendered.split("<script>")[0]
    assert "6 Forget it" in markup
    for tone in ("green", "yellow", "blue", "orange", "gray"):
        assert f"personal-priority__button tone-{tone}\"" in markup
    assert "personal-priority__button tone-dark selected" in markup


def test_priority_six_is_valid_for_organizations_but_not_people():
    check_rating("priority", 6)
    with pytest.raises(ValueError, match="between 1 and 6"):
        db_personal_priorities.set_personal_priority(7, 3, 42, 7)
    with pytest.raises(ValueError, match="between 1 and 5"):
        db_people.set_person_value_rating(7, 3, 42, 6)


def test_filters_can_pick_forget_it_exactly():
    where, params = organizations._build_organization_filters("", "", "", "", personal_priority="6")
    assert "cup.priority = %s" in where and params == [6]
    conditions, params = [], []
    db_people._rating_filter(conditions, params, "company_priority.priority", "6")
    assert conditions == ["company_priority.priority = %s"] and params == [6]


def test_list_badges_carry_their_level_colour():
    contact = {"id": 7, "kind": "organization", "name": "Acme", "description": None, "company": None,
               "city": "Ulm", "pipeline_stage": None, "deals": [], "last_contact": "2026-10-04", "people": [],
               "priority": 6, "long_term_value": 3, "short_term_value": 1}
    app.dependency_overrides[require_login] = lambda: "admin"
    try:
        with patch("gcrm.api.routers.contact_feed.get_contact_feed", return_value=[contact]):
            body = TestClient(app).get("/contact-feed/?lang=en").text.split("<tbody>")[1]
    finally:
        app.dependency_overrides.pop(require_login, None)
    assert 'personal-priority-badge tone-dark">P6<' in body
    assert 'personal-priority-badge tone-green" title="High">H<' in body
    assert 'personal-priority-badge tone-blue" title="Low">L<' in body
