"""Judge against the real schema: opportunity analysis only for companies the scout rated
ready, and the dropped companies still pinned on the Maps list."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_opportunities import get_organizations_needing_opportunity_analysis
from gcrm.tools.map_pins import dropped_but_pinned, record_pin, remove_pin

pytestmark = pytest.mark.integration


def add_company(name: str, stage: str, status: str) -> tuple[int, int]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO contacts (name, city, workspace_id) VALUES (%s, 'Untermeitingen', %s) RETURNING id",
                    (name, workspace_id))
        contact_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status) "
                    "VALUES (%s, offer_id_for(%s, 'consulting'), %s, %s, %s)",
                    (workspace_id, workspace_id, contact_id, stage, status))
    return workspace_id, contact_id


def test_opportunity_analysis_only_picks_ready_companies(clean_database):
    _, ready = add_company("Faist Systeme GmbH", "suspect", "ready")
    add_company("Auto Frey GmbH", "not_in_pipeline", "dropped")
    add_company("Meile GmbH", "candidate", "none")
    assert [row["id"] for row in get_organizations_needing_opportunity_analysis(limit=50)] == [ready]


def test_dropped_companies_still_pinned_are_listed_and_removed_pins_are_not(clean_database):
    workspace_id, dropped = add_company("Auto Frey GmbH", "not_in_pipeline", "dropped")
    _, kept = add_company("Faist Systeme GmbH", "suspect", "ready")
    _, unpinned = add_company("Action", "not_in_pipeline", "dropped")
    record_pin(dropped, "0x1:0x1", "Auto Frey GmbH")
    record_pin(kept, "0x2:0x2", "FAIST Systeme GmbH")
    removed = record_pin(unpinned, "0x3:0x3", "Action")
    remove_pin(removed["id"])
    assert [row["id"] for row in dropped_but_pinned(workspace_id)] == [dropped]
