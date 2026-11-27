"""Saved calculator figures on the real schema: per account, per workspace, encrypted."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_income_inputs import delete_inputs, load_inputs, save_inputs
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


@pytest.fixture
def accounts(clean_database):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES ('other-customer', 'Other') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        second = cursor.fetchone()["id"]
        ids = []
        for email, workspace in (("a@example.test", first), ("b@example.test", first), ("c@example.test", second)):
            cursor.execute("INSERT INTO users (email, password_hash, role, workspace_id) "
                           "VALUES (%s, 'hash', 'admin', %s) RETURNING id", (email, workspace))
            ids.append(cursor.fetchone()["id"])
    return first, second, ids


def test_save_load_overwrite_and_delete(accounts):
    first, _, (alice, _, _) = accounts
    with workspace_scope(first):
        assert load_inputs(alice) is None
        save_inputs(alice, {"consulting": "10"})
        save_inputs(alice, {"consulting": "20"})
        assert load_inputs(alice) == {"consulting": "20"}
        delete_inputs(alice)
        assert load_inputs(alice) is None


def test_each_account_sees_only_its_own_figures(accounts):
    first, _, (alice, bob, _) = accounts
    with workspace_scope(first):
        save_inputs(alice, {"consulting": "10"})
        assert load_inputs(bob) is None
        delete_inputs(bob)
        assert load_inputs(alice) == {"consulting": "10"}


def test_another_workspace_cannot_read_or_write_them(accounts):
    first, second, (alice, _, carol) = accounts
    with workspace_scope(first):
        save_inputs(alice, {"consulting": "10"})
    with workspace_scope(second):
        assert load_inputs(alice) is None
        delete_inputs(alice)
        with pytest.raises(Exception):
            save_inputs(alice, {"consulting": "99"})
        save_inputs(carol, {"consulting": "5"})
    with workspace_scope(first):
        assert load_inputs(alice) == {"consulting": "10"}


def test_the_database_holds_only_ciphertext_and_forgets_it_with_the_account(accounts):
    first, _, (alice, _, _) = accounts
    with workspace_scope(first):
        save_inputs(alice, {"disability_allowance": "2120"})
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT data_encrypted FROM income_calculator_inputs WHERE user_id = %s", (alice,))
        assert "2120" not in cursor.fetchone()["data_encrypted"]
        cursor.execute("DELETE FROM users WHERE id = %s", (alice,))
        cursor.execute("SELECT count(*) AS n FROM income_calculator_inputs")
        assert cursor.fetchone()["n"] == 0
