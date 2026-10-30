"""Guards behind the code-scanning alerts: offer slugs and SQL aliases that reach
SQL text, the old /contacts redirect, and what the area research run logs."""
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.tools.db_deals import offer_id_sql, organization_deal_join


def test_offer_slug_reaches_sql_only_when_it_is_a_plain_slug():
    assert offer_id_sql("c.workspace_id", "notes-world") == "offer_id_for(c.workspace_id, 'notes-world')"


@pytest.mark.parametrize("slug", ["consulting\n", "x' OR '1'='1", "Consulting", "-lead", "", "a" * 41, None, 3])
def test_anything_else_is_refused_before_it_reaches_sql(slug):
    with pytest.raises(ValueError):
        offer_id_sql("c.workspace_id", slug)


@pytest.mark.parametrize("alias", ["c\n", "c; DROP TABLE deals", "C", "1c"])
def test_sql_aliases_must_be_plain_identifiers(alias):
    with pytest.raises(ValueError):
        organization_deal_join(alias, "d")


@pytest.mark.parametrize("old,new", [
    ("/contacts/42?tab=notes", "/organizations/42?tab=notes"),
    ("/contacts/", "/organizations/"),
    ("/contacts//evil.test", "/organizations//evil.test"),  # still a path on this site
])
def test_old_contact_links_land_on_organizations_inside_this_site(old, new):
    response = TestClient(app).get(old, follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == new


def test_area_research_logs_the_area_id_but_not_its_coordinates(caplog):
    from gcrm.supervisor import run_research

    area = {"city": "Augsburg", "country": "DE", "latitude": 48.3705, "longitude": 10.8978, "radius_m": 5000}
    with patch("sys.argv", ["run_research", "--area-id", "7", "--levels", "1"]), \
         patch("gcrm.tools.get_area", return_value=area), \
         patch("gcrm.tools.get_llm"), \
         patch("gcrm_research_agent.create_research_agent", side_effect=RuntimeError("stop")), \
         caplog.at_level(logging.INFO):
        with pytest.raises(RuntimeError):
            run_research.main()
    assert "Researching area #7 (r=5000m)" in caplog.text
    assert "48.37" not in caplog.text and "10.89" not in caplog.text
