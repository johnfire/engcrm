"""The data backup on the real schema: what is in the ZIP, and that one workspace's
backup never holds another workspace's rows."""
import csv
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from gcrm.backup_export import FILES, build_backup, neutralize_formula
from gcrm.db.connection import db
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale, start_subscription
from gcrm.tools.deal_records import get_deals
from gcrm.tools.follow_ups import create_follow_up
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration


def _workspace(slug: str) -> int:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES (%s, %s) "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id", (slug, slug))
        return cursor.fetchone()["id"]


def _fill(workspace: int, org: str, person: str, note: str, euros: str) -> dict:
    """An organization, its person, a sale and a subscription inside one workspace."""
    with workspace_scope(workspace):
        contact = save_organization(org, "Augsburg", source="test_fixture", notes=note,
                                    email=f"info@{org.split()[0].lower()}.example")
        human = save_person(person, source="test_fixture", contact_id=contact)
        deal = next(d["id"] for d in get_deals("organization", contact) if d["offer_slug"] == "consulting")
        add_deal_sale(deal, euros, date(2026, 11, 3), f"Job for {org}", workspace, status="booked")
        start_subscription(deal, "49", date(2026, 11, 1))
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO interactions (contact_id, interaction_date, method, summary, workspace_id) "
                           "VALUES (%s, %s, 'phone', %s, %s)", (contact, date(2026, 11, 4), f"Called {org}", workspace))
    return {"contact": contact, "person": human, "deal": deal}


@pytest.fixture
def two_workspaces(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
    second = _workspace("other-customer")
    _fill(first, "Brandt Maschinenbau", "Mara Brandt", "first workspace secret note", "2400")
    _fill(second, "Kessler Logistik", "Jonas Kessler", "second workspace secret note", "9100")
    return first, second


def _deal_of(workspace: int) -> int:
    with workspace_scope(workspace), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM deals ORDER BY id LIMIT 1")
        return cursor.fetchone()["id"]


def _read(archive: bytes) -> dict[str, list[dict]]:
    out = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for name in z.namelist():
            if name.endswith(".csv"):
                text = z.read(name).decode("utf-8-sig")
                out[name] = list(csv.DictReader(io.StringIO(text)))
    return out


def test_the_zip_has_one_csv_per_kind_a_readme_and_a_manifest(two_workspaces):
    first, _ = two_workspaces
    archive, manifest = build_backup(first)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = set(z.namelist())
        assert names == set(FILES) | {"README.txt", "manifest.json"}
        assert json.loads(z.read("manifest.json"))["counts"] == manifest["counts"]
        assert z.read("organizations.csv").startswith(b"\xef\xbb\xbf")  # BOM: Excel reads umlauts right
    assert manifest["counts"]["organizations.csv"] == 1 and manifest["workspace_id"] == first
    rows = _read(archive)
    (org,) = rows["organizations.csv"]
    assert (org["name"], org["city"], org["notes"]) == ("Brandt Maschinenbau", "Augsburg", "first workspace secret note")
    (human,) = rows["people.csv"]
    assert human["name"] == "Mara Brandt" and human["organization_name"] == "Brandt Maschinenbau"
    (sale,) = rows["sales.csv"]
    assert (sale["status"], Decimal(sale["amount_eur"]), sale["owner_name"]) == ("booked", Decimal("2400"), "Brandt Maschinenbau")
    (sub,) = rows["subscriptions.csv"]
    assert Decimal(sub["amount_eur_month"]) == Decimal("49") and sub["started_on"] == "2026-11-01"
    (act,) = rows["activities.csv"]
    assert act["summary"] == "Called Brandt Maschinenbau" and act["organization_name"] == "Brandt Maschinenbau"
    assert any(row["slug"] == "consulting" for row in rows["offers.csv"])


def test_contracts_and_their_links_are_exported_and_sales_name_their_series_and_contract_apart(two_workspaces):
    first, second = two_workspaces
    with workspace_scope(first), db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contract_id FROM sales")
        contract = cursor.fetchone()["contract_id"]
        cursor.execute("INSERT INTO contract_links (workspace_id, contract_id, label, url) "
                       "VALUES (%s, %s, 'Syllabus', 'https://example.org/syllabus')", (first, contract))
    with workspace_scope(second), db() as connection:
        connection.cursor().execute("INSERT INTO contract_links (workspace_id, contract_id, label, url) "
                                    "SELECT %s, contract_id, 'Kessler secret', 'https://example.org/kessler' FROM sales",
                                    (second,))
    archive, manifest = build_backup(first)
    rows = _read(archive)
    assert {"contracts.csv", "contract_links.csv"} <= set(rows) and {"contracts.csv", "contract_links.csv"} <= set(FILES)
    (sale,) = rows["sales.csv"]
    assert "series_id" in sale and "contract_id" in sale and sale["contract_id"] == str(contract)
    assert sale["series_id"] == ""                                  # a one-off sale has no series
    (row,) = rows["contracts.csv"]
    assert (row["id"], row["title"], row["kind"], row["owner_name"], row["assignment"]) == (
        str(contract), "Job for Brandt Maschinenbau", "other", "Brandt Maschinenbau", "")
    assert list(row) == ["id", "deal_id", "offer", "organization_id", "person_id", "owner_name", "title", "kind",
                         "assignment", "contact_person_id", "created_at"]
    assert list(rows["contract_links.csv"][0]) == ["id", "contract_id", "label", "url", "sort_order", "created_at"]
    (link,) = rows["contract_links.csv"]
    assert (link["contract_id"], link["label"], link["url"]) == (str(contract), "Syllabus", "https://example.org/syllabus")
    assert manifest["counts"]["contracts.csv"] == 1 and manifest["counts"]["contract_links.csv"] == 1
    assert manifest["format_version"] == 2          # sales.csv's contract_id changed meaning (it was the series id)
    everything = " ".join(row_text for name in ("contracts.csv", "contract_links.csv") for row_text in [str(rows[name])])
    assert "Kessler" not in everything


def test_a_series_keeps_its_series_id_and_the_readme_explains_both_columns(two_workspaces):
    first, _ = two_workspaces
    with workspace_scope(first):
        deal = _deal_of(first)
        add_deal_sale(deal, "1200", date(2026, 11, 3), "Course", first, status="booked", expected_on=date(2027, 1, 1), months=3)
    archive, _ = build_backup(first)
    payments = [r for r in _read(archive)["sales.csv"] if r["description"] == "Course"]
    assert len(payments) == 3 and len({r["series_id"] for r in payments}) == 1 and payments[0]["series_id"]
    assert len({r["contract_id"] for r in payments}) == 1 and payments[0]["contract_id"] != payments[0]["series_id"]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        readme = z.read("README.txt").decode()
    assert "contracts.csv" in readme and "contract_links.csv" in readme
    assert "tied by series_id" in readme and "contract_id" in readme


def test_one_workspaces_backup_never_contains_another_workspaces_data(two_workspaces):
    first, second = two_workspaces
    for mine, theirs_words in ((first, ("Kessler", "9100", "second workspace", "Jonas")),
                               (second, ("Brandt", "2400", "first workspace", "Mara"))):
        archive, _ = build_backup(mine)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            everything = " ".join(z.read(n).decode("utf-8-sig") for n in z.namelist())
        for word in theirs_words:
            assert word not in everything, f"workspace {mine}'s backup leaked {word!r}"


def test_backup_includes_every_follow_up_without_cross_workspace_leaks(two_workspaces):
    first, second = two_workspaces
    for workspace, owner, text in [(first, "Brandt Maschinenbau", "Send private proposal"),
                                   (second, "Kessler Logistik", "Call private contact")]:
        with workspace_scope(workspace), db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM contacts WHERE name=%s", (owner,))
            organization = cursor.fetchone()["id"]
        with workspace_scope(workspace):
            deal = get_deals("organization", organization)[0]
            create_follow_up(deal_id=deal["id"], task_type="commitment", task_text=text)
    rows = _read(build_backup(first)[0])["follow_ups.csv"]
    assert [row["task_text"] for row in rows] == ["Send private proposal"]


def test_the_backup_runs_with_the_workspace_enforced_by_the_database(two_workspaces):
    """Even with the explicit workspace filter removed from a query, row security would hold:
    build_backup must enter the workspace scope itself rather than trust its caller."""
    first, second = two_workspaces
    with workspace_scope(second):  # a caller sitting in the wrong workspace
        archive, manifest = build_backup(first)
    assert manifest["workspace_id"] == first
    assert [r["name"] for r in _read(archive)["organizations.csv"]] == ["Brandt Maschinenbau"]


def test_deleted_rows_and_secrets_are_not_exported(two_workspaces):
    first, _ = two_workspaces
    with db() as connection:
        connection.cursor().execute("UPDATE contacts SET deleted_at = NOW() WHERE workspace_id = %s", (first,))
    archive, manifest = build_backup(first)
    assert manifest["counts"]["organizations.csv"] == 0
    rows = _read(archive)
    assert rows["organizations.csv"] == [] and rows["sales.csv"] == [] and rows["activities.csv"] == []
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert not {"users.csv", "audit_log.csv", "sessions.csv"} & set(z.namelist())
        text = " ".join(z.read(n).decode("utf-8-sig") for n in z.namelist()).lower()
    assert "password_hash" not in text and "mfa_secret" not in text and "token_hash" not in text


@pytest.mark.parametrize("typed,stored", [
    ("=HYPERLINK(\"http://evil.example\")", "'=HYPERLINK(\"http://evil.example\")"),
    ("@SUM(A1)", "'@SUM(A1)"),
    ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
    ("-2+3", "-2+3"),            # a number stays a number
    ("+49 821 123456", "+49 821 123456"),   # a phone number stays a phone number
    ("Müller & Söhne", "Müller & Söhne"),
    ("", ""), (None, ""), (5, "5"),
])
def test_a_typed_in_formula_never_runs_in_a_spreadsheet(typed, stored):
    assert neutralize_formula(typed) == stored


def test_the_plan_is_exported_with_the_new_sales_you_expect_each_month(two_workspaces):
    from gcrm.tools.income_plan import save_expected_new_sales
    first, second = two_workspaces
    with workspace_scope(first):
        save_expected_new_sales(Decimal("1000"))                      # no monthly need entered: the row still exports
    archive, manifest = build_backup(first)
    (plan,) = _read(archive)["income_plan.csv"]
    assert plan["expected_new_monthly"] == "1000.00" and plan["monthly_need"] == ""
    assert plan["expected_new_campaign"] == ""                                      # no end
    assert manifest["counts"]["income_plan.csv"] == 1
    assert _read(build_backup(second)[0])["income_plan.csv"] == []
