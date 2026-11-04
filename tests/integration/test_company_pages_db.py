"""Company LinkedIn/XING pages against the real schema: saving keeps a page already
stored, a company with no page is still marked checked, and enrichment picks up a company
that has an email but was never checked for its pages — once."""
import pytest

from gcrm.db.connection import db
from gcrm.tools.db_organizations import get_organizations_needing_enrichment, save_company_pages

pytestmark = pytest.mark.integration


def add_contact(name: str, email: str = "", **columns) -> int:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        workspace_id = cur.fetchone()["id"]
        names = ", ".join(["name", "city", "email", "workspace_id", *columns])
        marks = ", ".join(["%s"] * (4 + len(columns)))
        cur.execute(f"INSERT INTO contacts ({names}) VALUES ({marks}) RETURNING id",
                    (name, "Untermeitingen", email, workspace_id, *columns.values()))
        return cur.fetchone()["id"]


def pages_of(contact_id: int) -> dict:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT linkedin_url, xing_url, company_pages_checked_at FROM contacts WHERE id = %s",
                    (contact_id,))
        return dict(cur.fetchone())


def test_saving_keeps_a_page_already_stored_and_fills_the_missing_one(clean_database):
    contact_id = add_contact("Faist Systeme GmbH", linkedin_url="https://www.linkedin.com/company/kept/")
    save_company_pages(contact_id, linkedin_url="https://www.linkedin.com/company/other/",
                       xing_url="https://www.xing.com/pages/faist-systeme-gmbh")
    pages = pages_of(contact_id)
    assert pages["linkedin_url"] == "https://www.linkedin.com/company/kept/"
    assert pages["xing_url"] == "https://www.xing.com/pages/faist-systeme-gmbh"
    assert pages["company_pages_checked_at"] is not None


def test_no_page_found_is_still_marked_checked(clean_database):
    contact_id = add_contact("Meile GmbH")
    save_company_pages(contact_id)
    assert pages_of(contact_id)["company_pages_checked_at"] is not None


def test_enrichment_picks_up_an_unchecked_company_once_even_with_an_email(clean_database):
    contact_id = add_contact("Meile GmbH", email="info@meile.de")
    assert contact_id in {row["id"] for row in get_organizations_needing_enrichment(limit=50)}
    save_company_pages(contact_id)
    assert contact_id not in {row["id"] for row in get_organizations_needing_enrichment(limit=50)}


def test_a_dead_end_without_an_email_still_gets_its_pages_checked_once(clean_database):
    contact_id = add_contact("Ghost GmbH", research_exhausted=True)
    assert contact_id in {row["id"] for row in get_organizations_needing_enrichment(limit=50)}
    save_company_pages(contact_id)
    assert contact_id not in {row["id"] for row in get_organizations_needing_enrichment(limit=50)}
