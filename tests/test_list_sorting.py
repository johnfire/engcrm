"""Requested sort choices reach the database rather than falling back to creation date."""
from unittest.mock import MagicMock, patch

import pytest

from gcrm.api.routers.organizations import _sort_column
from gcrm.tools.db_contact_feed import get_contact_feed
from gcrm.tools.db_people import get_people


@pytest.mark.parametrize("sort,column", [("city", "lower(city)"), ("kind", "kind"),
                                         ("pipeline_stage", "stage_sort_key"), ("name", "lower(name)"),
                                         ("last_contact", "last_contact")])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_feed_sorts_before_pagination(sort, column, direction):
    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = []
    with patch("gcrm.tools.db_contact_feed.db") as database:
        database.return_value.__enter__.return_value = connection
        get_contact_feed(sort=sort, dir=direction, page=2)
    query, parameters = connection.cursor.return_value.execute.call_args.args
    # Out-of-pipeline contacts always go last; the requested sort applies within each group.
    assert (f"ORDER BY cardinality(array_remove(deal_stages, 'not_in_pipeline')) = 0, "
            f"{column} {direction.upper()} NULLS LAST") in query
    assert parameters[-2:] == [50, 50]


@pytest.mark.parametrize("offer", ["consulting", None])
@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("sort", ["pipeline_stage", "last_contact"])
def test_people_sort_requested_field(sort, direction, offer):
    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = []
    with patch("gcrm.tools.db_people.db") as database:
        database.return_value.__enter__.return_value = connection
        get_people(sort=sort, dir=direction, offer=offer)
    query = connection.cursor.return_value.execute.call_args.args[0]
    order = query.split("ORDER BY ")[-1]
    assert f"{direction.upper()} NULLS LAST, person.id" in order
    assert "person.created_at" not in order
    expected = "last_contact" if sort == "last_contact" else "x.pipeline_stage"
    assert expected in query


@pytest.mark.parametrize("offer", ["consulting", None])
def test_organization_stage_sort_uses_displayed_deals(offer):
    expression = _sort_column("pipeline_stage", offer)
    assert "x.pipeline_stage" in expression and "x.contact_id = c.id" in expression
