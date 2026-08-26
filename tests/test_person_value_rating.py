"""Private per-user "value as a contact" ratings for people stay private,
bounded, and auditable — mirrors test_personal_priorities.py, which covers
the same mechanism for the person's company."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gcrm.api.routers import people
from gcrm.api.routers.people import PersonValueRatingBody, update_person_value_rating
from gcrm.api.templates import templates
from gcrm.i18n import translate
from gcrm.tools import db_people


def _mock_database(*fetchone_values):
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(fetchone_values)
    connection = MagicMock()
    connection.cursor.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return context, cursor


def test_get_person_value_rating_returns_only_the_requested_users_value():
    context, cursor = _mock_database({"priority": 2})
    with patch.object(db_people, "db", return_value=context):
        rating = db_people.get_person_value_rating(7, 3, 42)

    assert rating == 2
    assert cursor.execute.call_args.args[1] == (7, 3, 42)


def test_set_person_value_rating_upserts_a_valid_value():
    context, cursor = _mock_database({"exists": 1}, {"priority": 4})
    with patch.object(db_people, "db", return_value=context):
        stored = db_people.set_person_value_rating(7, 3, 42, 4)

    assert stored == (True, 4)
    assert "ON CONFLICT (user_id, person_id)" in cursor.execute.call_args_list[1].args[0]


def test_clear_person_value_rating_deletes_only_the_users_row():
    context, cursor = _mock_database({"exists": 1})
    with patch.object(db_people, "db", return_value=context):
        stored = db_people.set_person_value_rating(7, 3, 42, None)

    assert stored == (True, None)
    assert "DELETE FROM person_user_priorities" in cursor.execute.call_args_list[1].args[0]
    assert cursor.execute.call_args_list[1].args[1] == (7, 3, 42)


def test_set_person_value_rating_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="between 1 and 5"):
        db_people.set_person_value_rating(7, 3, 42, 6)


def test_set_person_value_rating_hides_cross_workspace_people():
    context, _cursor = _mock_database(None)
    with patch.object(db_people, "db", return_value=context):
        stored = db_people.set_person_value_rating(7, 3, 42, 1)

    assert stored == (False, None)


def test_web_user_can_set_own_rating_and_action_is_audited():
    request = SimpleNamespace(session={"user_id": 7, "workspace_id": 3})
    with (
        patch(
            "gcrm.api.routers.people.set_person_value_rating",
            return_value=(True, 4),
        ) as save_rating,
        patch("gcrm.api.routers.people.log_audit") as log_audit,
    ):
        response = update_person_value_rating(
            42,
            PersonValueRatingBody(priority=4),
            request,
        )

    assert response == {"value_rating": 4}
    save_rating.assert_called_once_with(7, 3, 42, 4)
    assert log_audit.call_args.args[2:] == (
        "person.value_rating_changed",
        "person:42",
        "set:4",
    )


def test_contact_value_rating_partial_marks_only_the_users_selected_value():
    template = templates.env.get_template("partials/contact_value_rating.html")
    rendered = template.render(
        person={"id": 42, "value_rating": 4},
        request=SimpleNamespace(session={"user_id": 7}),
        t=lambda key: translate(key, "en"),
    )

    markup = rendered.split("<script>")[0]  # the script text itself quotes aria-pressed="true"
    assert "Only you can see this rating." in markup
    assert 'data-priority-value="4"' in markup
    assert markup.count('aria-pressed="true"') == 1


def test_web_shared_admin_cannot_own_person_value_rating():
    request = SimpleNamespace(session={"user_id": None, "workspace_id": None})
    with pytest.raises(people.HTTPException) as error:
        update_person_value_rating(
            42,
            PersonValueRatingBody(priority=1),
            request,
        )

    assert error.value.status_code == 403
