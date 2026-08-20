"""Personal prospect priorities stay private, bounded, and auditable."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gcrm.api.routers import organizations
from gcrm.api.routers.organizations import PersonalPriorityBody, update_personal_priority
from gcrm.api.templates import templates
from gcrm.i18n import translate
from gcrm.tools import db_personal_priorities


def _mock_database(*fetchone_values):
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(fetchone_values)
    connection = MagicMock()
    connection.cursor.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return context, cursor


def test_get_personal_priority_returns_only_the_requested_users_value():
    context, cursor = _mock_database({"priority": 2})
    with patch.object(db_personal_priorities, "db", return_value=context):
        priority = db_personal_priorities.get_personal_priority(7, 3, 42)

    assert priority == 2
    assert cursor.execute.call_args.args[1] == (7, 3, 42)


def test_set_personal_priority_upserts_a_valid_value():
    context, cursor = _mock_database({"exists": 1}, {"priority": 1})
    with patch.object(db_personal_priorities, "db", return_value=context):
        stored = db_personal_priorities.set_personal_priority(7, 3, 42, 1)

    assert stored == (True, 1)
    assert "ON CONFLICT (user_id, contact_id)" in cursor.execute.call_args_list[1].args[0]


def test_clear_personal_priority_deletes_only_the_users_row():
    context, cursor = _mock_database({"exists": 1})
    with patch.object(db_personal_priorities, "db", return_value=context):
        stored = db_personal_priorities.set_personal_priority(7, 3, 42, None)

    assert stored == (True, None)
    assert "DELETE FROM contact_user_priorities" in cursor.execute.call_args_list[1].args[0]
    assert cursor.execute.call_args_list[1].args[1] == (7, 3, 42)


def test_set_personal_priority_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="between 1 and 5"):
        db_personal_priorities.set_personal_priority(7, 3, 42, 6)


def test_set_personal_priority_hides_cross_workspace_organizations():
    context, _cursor = _mock_database(None)
    with patch.object(db_personal_priorities, "db", return_value=context):
        stored = db_personal_priorities.set_personal_priority(7, 3, 42, 1)

    assert stored == (False, None)


def test_web_spectator_can_set_own_priority_and_action_is_audited():
    request = SimpleNamespace(session={"user_id": 7, "workspace_id": 3})
    with (
        patch(
            "gcrm.api.routers.organizations.set_personal_priority",
            return_value=(True, 2),
        ) as save_priority,
        patch("gcrm.api.routers.organizations.log_audit") as log_audit,
    ):
        response = update_personal_priority(
            42,
            PersonalPriorityBody(priority=2),
            request,
        )

    assert response == {"personal_priority": 2}
    save_priority.assert_called_once_with(7, 3, 42, 2)
    assert log_audit.call_args.args[2:] == (
        "contact.personal_priority_changed",
        "contact:42",
        "set:2",
    )


def test_organization_filters_scope_and_filter_the_current_users_priority():
    where, params = organizations._build_organization_filters(
        "cold",
        "",
        "",
        "",
        personal_priority="2",
        workspace_id=3,
    )

    assert "cup.priority = %s" in where
    assert "c.workspace_id = %s" in where
    assert params == ["cold", 2, 3]


def test_unrated_filter_uses_the_current_users_missing_row():
    where, params = organizations._build_organization_filters(
        "",
        "",
        "",
        "",
        personal_priority="unrated",
    )

    assert "cup.priority IS NULL" in where
    assert params == []


def test_personal_priority_partial_marks_only_the_users_selected_value():
    template = templates.env.get_template("partials/personal_priority.html")
    rendered = template.render(
        organization={"id": 42, "personal_priority": 1},
        request=SimpleNamespace(session={"user_id": 7}),
        t=lambda key: translate(key, "en"),
    )

    assert "Only you can see this rating." in rendered
    assert 'data-priority-value="1"' in rendered
    assert rendered.count('aria-pressed="true"') == 1


def test_web_shared_admin_cannot_own_personal_priority():
    request = SimpleNamespace(session={"user_id": None, "workspace_id": None})
    with pytest.raises(organizations.HTTPException) as error:
        update_personal_priority(
            42,
            PersonalPriorityBody(priority=1),
            request,
        )

    assert error.value.status_code == 403
