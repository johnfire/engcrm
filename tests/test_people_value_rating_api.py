"""Rating a person as a contact from the phone, and filtering by it. Each rating
belongs to the account that set it."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.tools import db_people

client = TestClient(main.app)


@pytest.fixture
def as_user():
    """Signed in with a personal account (user 5, workspace 1)."""
    main.app.dependency_overrides[require_jwt_payload] = lambda: {"sub": "admin", "uid": 5}
    with patch("gcrm.api.routers.api_people._personal_identity", return_value=(5, 1)):
        yield
    main.app.dependency_overrides.pop(require_jwt_payload, None)


@pytest.fixture
def as_shared_admin():
    main.app.dependency_overrides[require_jwt_payload] = lambda: {"sub": "admin"}
    with patch("gcrm.api.routers.api_people._personal_identity", return_value=(None, None)):
        yield
    main.app.dependency_overrides.pop(require_jwt_payload, None)


def test_a_rating_is_stored_for_the_signed_in_user(as_user):
    with patch("gcrm.api.routers.api_people.set_person_value_rating", return_value=(True, 2)) as setter, \
         patch("gcrm.api.routers.api_people.log_audit"):
        response = client.put("/api/people/7/value-rating", json={"rating": 2})
    assert response.status_code == 200 and response.json() == {"value_rating": 2}
    setter.assert_called_once_with(5, 1, 7, 2)


def test_null_clears_the_rating(as_user):
    with patch("gcrm.api.routers.api_people.set_person_value_rating", return_value=(True, None)) as setter, \
         patch("gcrm.api.routers.api_people.log_audit"):
        response = client.put("/api/people/7/value-rating", json={"rating": None})
    assert response.json() == {"value_rating": None}
    setter.assert_called_once_with(5, 1, 7, None)


def test_out_of_range_is_a_400_and_unknown_person_a_404(as_user):
    with patch("gcrm.api.routers.api_people.set_person_value_rating", side_effect=ValueError("x")):
        assert client.put("/api/people/7/value-rating", json={"rating": 9}).status_code == 400
    with patch("gcrm.api.routers.api_people.set_person_value_rating", return_value=(False, None)):
        assert client.put("/api/people/7/value-rating", json={"rating": 2}).status_code == 404


def test_the_shared_admin_login_has_no_ratings(as_shared_admin):
    with patch("gcrm.api.routers.api_people.set_person_value_rating") as setter:
        response = client.put("/api/people/7/value-rating", json={"rating": 2})
    assert response.status_code == 403
    setter.assert_not_called()


def test_the_list_filters_by_the_users_own_rating_together_with_the_stage(as_user):
    with patch("gcrm.api.routers.api_people.get_people", return_value=[]) as listing:
        response = client.get("/api/people?stage=candidate&value_rating=3%2B&page=1")
    assert response.status_code == 200
    assert listing.call_args.args[3] == 5
    assert listing.call_args.kwargs["value_rating"] == "3+" and listing.call_args.kwargs["stage"] == "candidate"


def test_a_person_comes_with_the_users_own_rating(as_user):
    with patch("gcrm.api.routers.api_people.get_person", return_value={"id": 7, "value_rating": 2}) as getter:
        response = client.get("/api/people/7")
    assert response.json()["value_rating"] == 2
    getter.assert_called_once_with(7, 5)


@pytest.mark.parametrize("value, fragment, param", [
    ("3", "person_priority.priority = %s", 3),
    ("3+", "person_priority.priority <= %s", 3),
    ("unrated", "person_priority.priority IS NULL", None),
])
def test_rating_filter_values(value, fragment, param):
    conditions, params = [], []
    db_people._rating_filter(conditions, params, "person_priority.priority", value)
    assert conditions == [fragment] and params == ([] if param is None else [param])


@pytest.mark.parametrize("value", ["", "6+", "+", "x", "3++"])
def test_anything_else_filters_nothing(value):
    conditions, params = [], []
    db_people._rating_filter(conditions, params, "person_priority.priority", value)
    assert conditions == [] and params == []


def test_the_rating_condition_is_built_from_constants_not_the_request():
    conn, cur = MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = []
    with patch("gcrm.tools.db_people.db") as mock_db:
        mock_db.return_value.__enter__.return_value = conn
        db_people.get_people(user_id=5, value_rating="3+'; DROP TABLE people; --")
    assert "DROP" not in cur.execute.call_args.args[0]
