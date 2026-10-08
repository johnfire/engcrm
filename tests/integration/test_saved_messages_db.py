"""Exact text persistence, cross-account isolation, and optimistic updates."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_saved_messages import (
    create_saved_message,
    list_saved_messages,
    owns_saved_message,
    update_saved_message,
)
from gcrm.tools.db_users import create_user

pytestmark = pytest.mark.integration
WORDING = "  α\r\n\n🙂\t  "


def account(email):
    user_id = create_user(email, "test-only-hash", "admin")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT workspace_id FROM users WHERE id=%s", (user_id,))
        return user_id, cursor.fetchone()["workspace_id"]


def test_empty_library_and_exact_roundtrip_with_versioned_edits(clean_database):
    owner = account("wording@example.test")
    assert list_saved_messages(*owner) == []
    created = create_saved_message(*owner, " label ", WORDING)
    assert list_saved_messages(*owner) == [created]
    assert created["body"] == WORDING and created["version"] == 1
    updated = update_saved_message(*owner, created["id"], "changed", WORDING + "\n", 1)
    assert updated["body"] == WORDING + "\n" and updated["version"] == 2
    assert update_saved_message(*owner, created["id"], "stale", "x", 1) is None
    assert list_saved_messages(*owner) == [updated]
    assert owns_saved_message(*owner, created["id"])


def test_other_accounts_and_workspaces_cannot_read_or_change_wording(clean_database):
    owner = account("owner@example.test")
    other = account("other@example.test")
    created = create_saved_message(*owner, "label", WORDING)
    assert list_saved_messages(*other) == []
    assert update_saved_message(*other, created["id"], "wrong", "x", 1) is None
    assert not owns_saved_message(*other, created["id"])
    assert list_saved_messages(owner[0], owner[1] + 1000) == []
    assert not owns_saved_message(owner[0], owner[1] + 1000, created["id"])


def test_private_wording_is_removed_with_its_account(clean_database):
    owner = account("remove@example.test")
    create_saved_message(*owner, "label", WORDING)
    with db() as connection:
        connection.cursor().execute("DELETE FROM users WHERE id=%s", (owner[0],))
    assert list_saved_messages(*owner) == []
