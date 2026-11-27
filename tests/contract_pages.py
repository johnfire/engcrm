"""Where a deal's payment rows are shown: on its contracts' pages (the organization and person cards only list the
contracts). Real-database tests that look at payment rows read them from here."""
from gcrm.db.connection import db


def contract_pages(browser, deal_id: int) -> str:
    """The contract pages of every live sale of the deal, payments open, in the order the contracts were made."""
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT DISTINCT contract_id FROM sales WHERE deal_id = %s AND deleted_at IS NULL "
                       "ORDER BY contract_id", (deal_id,))
        contracts = [row["contract_id"] for row in cursor.fetchall()]
    assert contracts, "the deal has no sales"
    pages = [browser.get(f"/contracts/{contract}?open=payments&lang=en") for contract in contracts]
    assert all(page.status_code == 200 for page in pages)
    return "".join(page.text for page in pages)
