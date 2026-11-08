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


def test_one_workspaces_backup_never_contains_another_workspaces_data(two_workspaces):
    first, second = two_workspaces
    for mine, theirs_words in ((first, ("Kessler", "9100", "second workspace", "Jonas")),
                               (second, ("Brandt", "2400", "first workspace", "Mara"))):
        archive, _ = build_backup(mine)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            everything = " ".join(z.read(n).decode("utf-8-sig") for n in z.namelist())
        for word in theirs_words:
            assert word not in everything, f"workspace {mine}'s backup leaked {word!r}"


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
    assert manifest["counts"]["income_plan.csv"] == 1
    assert _read(build_backup(second)[0])["income_plan.csv"] == []
