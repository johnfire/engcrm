"""The calculator remembers each account's own figures, and still works when storage does not."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_login
from gcrm.api.routers.income_calculator import account_id
from gcrm.tools import db_income_inputs

client = TestClient(main.app)
ROUTER = "gcrm.api.routers.income_calculator"


def signed_in_as(user_id):
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[account_id] = lambda: user_id


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(account_id, None)


@pytest.fixture
def storage():
    with patch(f"{ROUTER}.load_inputs", return_value=None) as load, \
         patch(f"{ROUTER}.save_inputs") as save, patch(f"{ROUTER}.delete_inputs") as delete:
        yield load, save, delete


def test_saved_figures_fill_the_form_and_show_the_result_straight_away(storage):
    load, save, _ = storage
    load.return_value = {"consulting": "75000", "months_remaining": 4, "church_rate": 8}
    signed_in_as(7)
    page = client.get("/income-calculator").text
    load.assert_called_once_with(7)
    assert 'value="75000"' in page and 'value="4"' in page
    assert "income-calculator-hero" in page
    save.assert_not_called()


def test_with_nothing_saved_the_page_starts_empty(storage):
    signed_in_as(7)
    page = client.get("/income-calculator").text
    assert "income-calculator-hero" not in page and "income-calculator-empty" in page


def test_calculating_saves_the_figures_for_that_account(storage):
    _, save, _ = storage
    signed_in_as(7)
    response = client.post("/income-calculator", data={"consulting": "1234,50", "health_costs": "300"})
    assert response.status_code == 200 and "saved" in response.text.lower()
    user_id, values = save.call_args.args
    assert user_id == 7
    assert values["consulting"] == "1234.50" and values["health_costs"] == "300"
    json.dumps(values)  # storable as it is


def test_figures_that_do_not_validate_are_not_saved(storage):
    _, save, _ = storage
    signed_in_as(7)
    assert client.post("/income-calculator", data={"consulting": "-1"}).status_code == 422
    save.assert_not_called()


def test_the_shared_admin_login_has_no_account_so_nothing_is_stored(storage):
    load, save, _ = storage
    signed_in_as(None)
    page = client.get("/income-calculator").text
    client.post("/income-calculator", data={"consulting": "10"})
    load.assert_not_called()
    save.assert_not_called()
    assert "personal account" in page


def test_clearing_deletes_only_that_accounts_figures(storage):
    _, _, delete = storage
    signed_in_as(7)
    response = client.post("/income-calculator/clear", follow_redirects=False)
    delete.assert_called_once_with(7)
    assert response.status_code == 303 and response.headers["location"] == "/income-calculator"


def test_the_calculator_still_works_when_saved_figures_cannot_be_read(storage):
    load, _, _ = storage
    load.side_effect = RuntimeError("database away")
    signed_in_as(7)
    response = client.get("/income-calculator")
    assert response.status_code == 200 and "could not be loaded" in response.text


def test_the_result_is_shown_even_when_saving_fails(storage):
    _, save, _ = storage
    save.side_effect = RuntimeError("database away")
    signed_in_as(7)
    response = client.post("/income-calculator", data={"consulting": "75000"})
    assert response.status_code == 200
    assert "could not be saved" in response.text and "income-calculator-hero" in response.text


def test_stored_figures_that_no_longer_validate_are_ignored(storage):
    load, _, _ = storage
    load.return_value = {"consulting": "not a number"}
    signed_in_as(7)
    response = client.get("/income-calculator")
    assert response.status_code == 200 and "income-calculator-hero" not in response.text


def test_a_failure_never_logs_the_figures(storage, caplog):
    _, save, _ = storage
    save.side_effect = RuntimeError("row (98765.43) rejected")
    signed_in_as(7)
    client.post("/income-calculator", data={"consulting": "98765.43"})
    assert "98765" not in caplog.text


def fake_db(row=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    connection = MagicMock()
    connection.cursor.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return MagicMock(return_value=context), cursor


def test_the_stored_value_is_encrypted_and_reads_back():
    factory, cursor = fake_db()
    with patch.object(db_income_inputs, "db", factory):
        db_income_inputs.save_inputs(7, {"disability_allowance": "2120", "consulting": "75000"})
    stored = cursor.execute.call_args.args[1][1]
    assert "2120" not in stored and "disability" not in stored and "75000" not in stored
    factory, _ = fake_db({"data_encrypted": stored})
    with patch.object(db_income_inputs, "db", factory):
        assert db_income_inputs.load_inputs(7) == {"disability_allowance": "2120", "consulting": "75000"}


def test_the_emailed_backup_does_not_contain_the_calculator_table():
    from gcrm.backup_export import FILES
    assert not any("income_calculator" in sql for sql in FILES.values())
