"""Mobile list endpoints: the people filters and paging, the organization list's
LinkedIn / suppressed filters, and the reachable-fits route. DB mocked."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.tools import db_people

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}
VIEWER = {"Authorization": f"Bearer {create_token('viewer')}"}


def mock_conn(rows=()):
    cursor = MagicMock()
    cursor.fetchall.return_value = list(rows)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


class TestPeopleEndpoint:
    def get(self, params=None, headers=ADMIN):
        with patch("gcrm.api.routers.api_people.get_people", return_value=[{"id": 1}]) as people:
            response = client.get("/api/people", params=params or {}, headers=headers)
        return response, people

    def test_without_a_page_the_whole_list_comes_back_as_older_builds_expect(self):
        response, people = self.get()
        assert response.status_code == 200
        assert people.call_args.kwargs == {"linkedin": "", "stage": "", "city": ""}

    def test_a_page_asks_for_fifty_from_the_right_offset(self):
        _, people = self.get({"page": 3})
        assert people.call_args.kwargs["limit"] == 50 and people.call_args.kwargs["offset"] == 100

    def test_filters_are_passed_through(self):
        _, people = self.get({"stage": "prospect", "linkedin": "unlinked", "search": "anna", "sort": "connected_on"})
        assert people.call_args.args[:3] == ("anna", "connected_on", "desc")
        assert people.call_args.kwargs["stage"] == "prospect" and people.call_args.kwargs["linkedin"] == "unlinked"

    def test_a_city_is_passed_through(self):
        _, people = self.get({"city": "Ulm"})
        assert people.call_args.kwargs["city"] == "Ulm"

    def test_the_city_list_comes_back_with_head_counts(self):
        rows = [{"city": "Augsburg", "people": 3}, {"city": "Ulm", "people": 1}]
        with patch("gcrm.api.routers.api_people.get_person_cities", return_value=rows):
            response = client.get("/api/people/cities", headers=VIEWER)
        assert response.status_code == 200 and response.json() == rows

    @pytest.mark.parametrize("params", [{"stage": "bogus"}, {"linkedin": "maybe"}, {"page": 0}])
    def test_unknown_values_are_refused_not_ignored(self, params):
        response, people = self.get(params)
        assert response.status_code in (400, 422)
        people.assert_not_called()

    def test_none_means_no_stage_set(self):
        response, people = self.get({"stage": "none"})
        assert response.status_code == 200 and people.call_args.kwargs["stage"] == "none"


class TestGetPeoplePaging:
    def run(self, **kwargs):
        conn, cursor = mock_conn()
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            db_people.get_people(**kwargs)
        return cursor.execute.call_args.args

    def test_the_order_always_ends_on_the_id_so_pages_never_repeat_or_skip_people(self):
        sql, _ = self.run(sort="connected_on")
        assert "ORDER BY person.connected_on DESC NULLS LAST, person.id" in sql

    def test_limit_and_offset_are_bound_parameters(self):
        sql, params = self.run(limit=50, offset=100)
        assert sql.rstrip().endswith("LIMIT %s OFFSET %s")
        assert params[-2:] == [50, 100]

    def test_a_city_filters_ignoring_case_and_spaces_with_a_bound_parameter(self):
        sql, params = self.run(city="  Ulm ")
        assert "lower(trim(person.city)) = lower(%s)" in sql
        assert "Ulm" not in sql and params == ["Ulm"]

    def test_a_blank_city_means_every_city(self):
        sql, params = self.run(city="   ")
        assert "person.city)" not in sql and params == []

    def test_the_city_list_groups_spellings_that_differ_only_in_case(self):
        conn, cursor = mock_conn([{"city": "Ulm", "people": 2}])
        with patch("gcrm.tools.db_people.db") as mock_db:
            mock_db.return_value.__enter__.return_value = conn
            assert db_people.get_person_cities() == [{"city": "Ulm", "people": 2}]
        assert "GROUP BY lower(trim(city))" in cursor.execute.call_args.args[0]
        assert "FROM people\n" in cursor.execute.call_args.args[0]  # the table is `people`; `person` is only an alias in get_people

    def test_no_limit_means_no_limit_clause(self):
        sql, _ = self.run()
        assert "LIMIT" not in sql

    def test_a_negative_offset_is_clamped(self):
        _, params = self.run(limit=50, offset=-5)
        assert params[-1] == 0


class TestOrganizationList:
    def get(self, params):
        conn, cursor = mock_conn()
        with patch("gcrm.api.routers.api_organizations.db") as mock_db, \
             patch("gcrm.api.routers.api_organizations._personal_identity", return_value=(None, None)):
            mock_db.return_value.__enter__.return_value = conn
            response = client.get("/api/contacts", params=params, headers=ADMIN)
        return response, cursor.execute.call_args.args

    def test_linkedin_filter_asks_for_a_connection_there(self):
        response, (sql, _) = self.get({"linkedin": "1"})
        assert response.status_code == 200
        assert "k.is_linkedin_contact AND k.deleted_at IS NULL" in sql.split("GROUP BY")[0].split("WHERE")[-1]

    def test_suppressed_filter_accepts_only_the_known_flags(self):
        _, (sql, _) = self.get({"suppressed": "do_not_contact"})
        assert "c.do_not_contact = TRUE" in sql
        _, (sql, _) = self.get({"suppressed": "1; DROP TABLE contacts"})
        assert "DROP" not in sql and "= TRUE" not in sql

    def test_unknown_linkedin_value_filters_nothing(self):
        _, (sql, _) = self.get({"linkedin": "maybe"})
        assert "is_linkedin_contact" not in sql.split("GROUP BY")[0].split("WHERE")[-1]

    def test_the_order_ends_on_the_id(self):
        _, (sql, _) = self.get({})
        assert "NULLS LAST, c.id" in sql


class TestReachable:
    def test_returns_the_work_list_and_is_not_read_as_an_organization_id(self):
        rows = {"total": 1, "rows": [{"id": 4, "name": "Acme", "fit_score": 80,
                                      "people": [{"id": 9, "name": "Anna", "title": "CTO"}]}]}
        with patch("gcrm.api.routers.api_organizations.get_reachable_fits", return_value=rows) as fits, \
             patch("gcrm.api.routers.api_organizations._personal_identity", return_value=(3, 12)):
            response = client.get("/api/contacts/reachable", params={"page": 2}, headers=VIEWER)
        assert response.status_code == 200 and response.json() == rows
        fits.assert_called_once_with(2, 12)

    def test_needs_a_login(self):
        assert client.get("/api/contacts/reachable").status_code in (401, 403)
