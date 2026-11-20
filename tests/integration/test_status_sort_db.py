"""The mobile lists sort by status, best first, and every sort the app offers runs on real SQL."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gcrm.api.jwt_auth import create_token
from gcrm.api.main import app
from gcrm.db.connection import db
from gcrm.organization_state import STATUS_SORT_ORDER

pytestmark = pytest.mark.integration
HEADERS = {"Authorization": f"Bearer {create_token('admin')}"}
OPTIONS = (Path(__file__).parent.parent.parent / "engcrm-mobile" / "services" / "listSortOptions.ts").read_text()


@pytest.fixture
def statused_contacts(clean_database):
    """One organization and one person per status, then one with no deal: name = the status."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug='default'")
        workspace = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM offers WHERE workspace_id=%s AND slug='consulting'", (workspace,))
        offer = cursor.fetchone()["id"]
        for status in (*STATUS_SORT_ORDER, None):
            for table, column, interactions in (
                ("contacts", "contact_id", "INSERT INTO interactions (contact_id,interaction_date,method) VALUES (%s,CURRENT_DATE,'phone')"),
                ("people", "person_id", "INSERT INTO people_interactions (person_id,method,note) VALUES (%s,'call','status sort')"),
            ):
                cursor.execute(f"INSERT INTO {table} (name,workspace_id) VALUES (%s,%s) RETURNING id",
                               (f"Status {status or 'missing'}", workspace))
                owner = cursor.fetchone()["id"]
                if status:
                    cursor.execute(f"INSERT INTO deals (workspace_id,offer_id,{column},pipeline_stage,status) "
                                   "VALUES (%s,%s,%s,'prospect',%s)", (workspace, offer, owner, status))
                cursor.execute(interactions, (owner,))
    return TestClient(app)


def names(response, only_kind=None):
    assert response.status_code == 200, response.text
    return [row["name"].removeprefix("Status ") for row in response.json()
            if only_kind in (None, row.get("kind"))]


def expected(direction):
    order = list(STATUS_SORT_ORDER)
    return order if direction == "asc" else order[::-1]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_organizations_sort_by_status_with_no_deal_last(statused_contacts, direction):
    response = statused_contacts.get("/api/contacts", params={"sort": "status", "dir": direction, "search": "Status"},
                                     headers=HEADERS)
    assert names(response) == [*expected(direction), "missing"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_people_sort_by_status_with_no_deal_last(statused_contacts, direction):
    response = statused_contacts.get("/api/people", params={"sort": "status", "dir": direction, "search": "Status"},
                                     headers=HEADERS)
    assert names(response) == [*expected(direction), "missing"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_contact_feed_sorts_by_status_with_no_deal_last(statused_contacts, direction):
    response = statused_contacts.get("/api/contact-feed", params={"sort": "status", "dir": direction, "search": "Status"},
                                     headers=HEADERS)
    shown = names(response, "organization")
    assert shown == [*expected(direction), "missing"]
    assert names(response, "person") == shown


def offered(list_name):
    block = re.search(rf"export const {list_name}\b.*?= \[(.*?)\n\];", OPTIONS, re.S).group(1)
    return re.findall(r'key: "(\w+)"', block)


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("offer", ["all", "consulting"])
@pytest.mark.parametrize("path,list_name", [("/api/contacts", "ORGANIZATION_SORTS"), ("/api/people", "PERSON_SORTS"),
                                            ("/api/contact-feed", "CONTACT_SORTS")])
def test_every_sort_the_app_offers_runs_on_real_sql(statused_contacts, path, list_name, offer, direction):
    for key in offered(list_name):
        response = statused_contacts.get(path, params={"sort": key, "dir": direction, "offer": offer}, headers=HEADERS)
        assert response.status_code == 200, f"{path} sort={key} dir={direction} offer={offer}: {response.text[:300]}"
