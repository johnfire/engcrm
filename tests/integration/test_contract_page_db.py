"""One contract's page through real logins on the real schema: what it shows, who may change it, that every
change is checked, and that another workspace's (or a deleted) contract is a 404 everywhere."""
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.api.templates import eur
from gcrm.db.connection import db
from gcrm.tools.db_contracts import (
    add_link,
    delete_contract,
    get_contract,
    list_contracts,
    update_contract,
)
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_people import save_person
from gcrm.tools.deal_money import add_deal_sale
from gcrm.tools.deal_records import add_deal, get_deals
from gcrm.tools.revenue import business_revenue
from gcrm.workspace_context import workspace_scope

pytestmark = pytest.mark.integration
PASSWORD = "a-long-test-password-1"
TODAY = date.today()
ROOT = Path(__file__).parents[2]
CSRF_INPUT = r'(?:<input type="hidden" name="csrf_token" value="[^"]*">)?'      # the middleware adds one to every form


def _user(workspace, email, role="admin"):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (email, email.split("@")[0], hash_password(PASSWORD), role, workspace))


def _browser(email="owner@first.example"):
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False).status_code in (302, 303)
    return browser


def _consulting(owner_kind, owner_id):
    return next(d["id"] for d in get_deals(owner_kind, owner_id) if d["offer_slug"] == "consulting")


@pytest.fixture
def world(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    monkeypatch.setattr("gcrm.tools.db_people.geocode", lambda city, country: None)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        first = cursor.fetchone()["id"]
        cursor.execute("INSERT INTO workspaces (slug, name) VALUES ('other-customer', 'Other') "
                       "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id")
        second = cursor.fetchone()["id"]
    _user(first, "owner@first.example")
    _user(first, "viewer@first.example", role="spectator")
    _user(second, "owner@second.example")
    with workspace_scope(first):
        school = save_organization("VHS Musterstadt", "Augsburg", source="test_fixture")
        other_school = save_organization("Berufsschule Beispiel", "Ulm", source="test_fixture")
        coordinator = save_person("Mara Beispiel", source="test_fixture", contact_id=school)
        colleague = save_person("Tim Lehrer", source="test_fixture", contact_id=school)
        outsider = save_person("Olga Fremd", source="test_fixture", contact_id=other_school)
        freelancer = save_person("Pat Freelancer", source="test_fixture")
        with db() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT offer_id_for(%s, 'consulting') AS id", (first,))
            own_deal = add_deal("person", freelancer, cursor.fetchone()["id"])
        deal = _consulting("organization", school)
        add_deal_sale(deal, "2400", date(2026, 11, 8), "Year course", first, status="booked", expected_on=TODAY, months=4, hours="40")
        add_deal_sale(deal, "500", date(2026, 11, 9), "Single job", first, status="booked", expected_on=TODAY)
        add_deal_sale(own_deal, "300", date(2026, 11, 8), "Coaching block", first, status="booked")
    with workspace_scope(second):
        foreign_org = save_organization("Kessler Logistik", "Ulm", source="test_fixture")
        add_deal_sale(_consulting("organization", foreign_org), "9000", date(2026, 11, 8), "Kessler secret", second, status="booked")
        add_deal_sale(_consulting("organization", foreign_org), "100", date(2026, 11, 8), "Kessler gone", second, status="booked")
    ids = {}
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, title FROM contracts")
        for row in cursor.fetchall():
            ids[row["title"]] = row["id"]
    with workspace_scope(second):
        delete_contract(ids["Kessler gone"], second)
    return {"first": first, "second": second, "deal": deal, "contract": ids["Year course"], "single": ids["Single job"],
            "own": ids["Coaching block"], "foreign": ids["Kessler secret"], "deleted": ids["Kessler gone"],
            "coordinator": coordinator, "colleague": colleague, "outsider": outsider, "freelancer": freelancer}


def _title(contract):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT title FROM contracts WHERE id = %s", (contract,))
        return cursor.fetchone()["title"]


def _writes(contract):
    """Every way to change a contract over HTTP: (path, form data)."""
    return [
        (f"/contracts/{contract}", {"title": "Hijacked", "kind": "other", "assignment": "x", "contact_person_id": ""}),
        (f"/contracts/{contract}/delete", {}),
        (f"/contracts/{contract}/links", {"label": "x", "url": "https://example.org"}),
        (f"/contracts/{contract}/links/1/delete", {}),
        (f"/contracts/{contract}/links/1/move", {"direction": "up"}),
        (f"/contracts/{contract}/payments", {"amount_eur": "5", "status": "booked", "expected_on": ""}),
    ]


# --- the page ---------------------------------------------------------------

def test_the_page_shows_the_contract_its_customer_money_assignment_links_and_payments(world):
    with workspace_scope(world["first"]):
        update_contract(world["contract"], world["first"], "Year-long AI course", "teaching_course",
                        "Week 1: basics\nWeek 2: tools", world["coordinator"])
        add_link(world["contract"], world["first"], "Syllabus", "https://example.org/syllabus")
    html = _browser().get(f"/contracts/{world['contract']}?lang=en").text
    for text in ("Year-long AI course", "Teaching course", "VHS Musterstadt", "Consulting", "Mara Beispiel", "Week 1: basics",
                 "Week 2: tools", "Syllabus", "Payments", eur(2400), "40 h", f"{eur(60)}/h"):
        assert text in html, text
    assert f'href="/organizations/{get_contract_org(world)}"' in html and f'href="/people/{world["coordinator"]}"' in html
    money = re.search(r'class="detail-section contract-money".*?</section>', html, re.S).group(0)
    assert eur(2400) in money and eur(0) in money                      # value, and nothing collected yet: all of it still open
    assert '<a href="https://example.org/syllabus" target="_blank" rel="noopener noreferrer">Syllabus</a>' in html


def get_contract_org(world):
    with workspace_scope(world["first"]):
        return get_contract(world["contract"], world["first"])["organization_id"]


def test_the_payments_are_closed_until_asked_for_and_reuse_the_sale_controls_coming_back_to_this_page(world):
    browser = _browser()
    closed = browser.get(f"/contracts/{world['contract']}").text
    assert not re.search(r"\bopen\b", re.search(r'<details[^>]*id="payments"[^>]*>', closed).group(0))
    html = browser.get(f"/contracts/{world['contract']}?open=payments").text
    assert re.search(r"\bopen\b", re.search(r'<details[^>]*id="payments"[^>]*>', html).group(0))
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, series_id::text AS series FROM sales WHERE contract_id = %s ORDER BY series_part LIMIT 1", (world["contract"],))
        first = cursor.fetchone()
    back = f'<input type="hidden" name="next" value="/contracts/{world["contract"]}?open=payments" />'
    assert f'action="/deals/{world["deal"]}/sales/{first["id"]}/status"' in html and back in html
    assert f'action="/deals/{world["deal"]}/series/{first["series"]}/status"' in html            # the whole-contract status control
    assert html.count("sale--booked") == 4


def test_a_spectator_can_look_but_sees_no_way_to_change_anything_and_every_write_is_refused(world):
    viewer = _browser("viewer@first.example")
    page = viewer.get(f"/contracts/{world['contract']}?open=payments")
    assert page.status_code == 200 and "Year course" in page.text
    assert 'class="contract-edit"' not in page.text and f'action="/contracts/{world["contract"]}/delete"' not in page.text
    assert re.search(r'<fieldset class="contract-payments" disabled', page.text)
    for path, data in _writes(world["contract"]):
        assert viewer.post(path, data=data, follow_redirects=False).status_code == 403, path
    assert _title(world["contract"]) == "Year course"


def test_a_stranger_is_sent_to_the_login_for_the_page_and_every_write(world):
    stranger = TestClient(main.app)
    response = stranger.get(f"/contracts/{world['contract']}", follow_redirects=False)
    assert response.status_code in (302, 303, 307) and "login" in response.headers["location"]
    assert "Year course" not in response.text
    for path, data in _writes(world["contract"]):
        assert stranger.post(path, data=data, follow_redirects=False).status_code in (302, 303, 307, 403), path
    assert _title(world["contract"]) == "Year course"


@pytest.mark.parametrize("which", ["foreign", "deleted", "unknown"])
def test_another_workspaces_or_a_deleted_or_unknown_contract_is_a_404_on_the_page_and_on_every_write(world, which):
    contract = {"foreign": world["foreign"], "deleted": world["deleted"], "unknown": 987654}[which]
    owner = _browser()
    assert owner.get(f"/contracts/{contract}").status_code == 404
    for path, data in _writes(contract):
        assert owner.post(path, data=data, follow_redirects=False).status_code == 404, path
    assert _title(world["foreign"]) == "Kessler secret"
    with workspace_scope(world["second"]):
        assert get_contract(world["foreign"], world["second"])["links"] == []


def test_a_second_workspace_sees_its_own_contract_and_not_the_first_ones(world):
    second = _browser("owner@second.example")
    assert second.get(f"/contracts/{world['foreign']}").status_code == 200
    assert second.get(f"/contracts/{world['contract']}").status_code == 404


def test_the_list_links_to_a_page_that_exists(world):
    owner = _browser()
    html = owner.get("/contracts/").text
    href = re.search(r'<a class="contract-title" href="(/contracts/\d+)">', html).group(1)
    assert owner.get(href).status_code == 200


# --- editing -----------------------------------------------------------------

def test_an_admin_edits_the_contract_and_sees_the_change(world):
    owner = _browser()
    response = owner.post(f"/contracts/{world['contract']}", follow_redirects=False,
                          data={"title": "Year-long AI course", "kind": "teaching_course", "assignment": "Week 1: basics",
                                "contact_person_id": str(world["coordinator"])})
    assert response.status_code == 303 and response.headers["location"] == f"/contracts/{world['contract']}"
    html = owner.get(response.headers["location"]).text
    assert "Year-long AI course" in html and "Teaching course" in html and "Week 1: basics" in html and "Mara Beispiel" in html
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT target FROM audit_log WHERE action = 'contract.edited'")
        assert [row["target"] for row in cursor.fetchall()] == [f"contract:{world['contract']}"]


@pytest.mark.parametrize("data,words", [
    ({"title": "  ", "kind": "other", "assignment": "", "contact_person_id": ""}, "title"),
    ({"title": "x" * 201, "kind": "other", "assignment": "", "contact_person_id": ""}, "title"),
    ({"title": "Fine", "kind": "speech", "assignment": "", "contact_person_id": ""}, "kinds"),
    ({"title": "Fine", "kind": "other", "assignment": "x" * 20_001, "contact_person_id": ""}, "20,000"),
    ({"title": "Fine", "kind": "other", "assignment": "", "contact_person_id": "abc"}, "contact person"),
])
def test_a_bad_edit_shows_the_page_again_with_the_reason_and_saves_nothing(world, data, words):
    response = _browser().post(f"/contracts/{world['contract']}", data=data, follow_redirects=False)
    assert response.status_code == 400
    assert '<p class="error" role="alert">' in response.text and words in re.search(r'<p class="error" role="alert">(.*?)</p>', response.text, re.S).group(1)
    assert re.search(r'<details class="contract-edit" open', response.text)           # the form is open again
    assert _title(world["contract"]) == "Year course"


def test_the_reason_is_shown_in_german_to_a_german_reader(world):
    owner = _browser()
    owner.post("/settings/language", data={"ui_language": "de"})
    response = owner.post(f"/contracts/{world['contract']}", data={"title": " ", "kind": "other", "assignment": "", "contact_person_id": ""})
    assert response.status_code == 400 and "Titel" in response.text


def test_the_contact_picker_offers_only_people_of_the_customer_and_the_server_refuses_anyone_else(world):
    owner = _browser()
    html = owner.get(f"/contracts/{world['contract']}").text
    picker = re.search(r'<select name="contact_person_id">.*?</select>', html, re.S).group(0)
    assert "Mara Beispiel" in picker and "Tim Lehrer" in picker and "Olga Fremd" not in picker and "Pat Freelancer" not in picker
    for refused in (world["outsider"], world["freelancer"], 987654):
        response = owner.post(f"/contracts/{world['contract']}", follow_redirects=False,
                              data={"title": "Year course", "kind": "other", "assignment": "", "contact_person_id": str(refused)})
        assert response.status_code == 400 and "contact" in response.text.lower()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT contact_person_id FROM contracts WHERE id = %s", (world["contract"],))
        assert cursor.fetchone()["contact_person_id"] is None


def test_a_persons_own_contract_offers_only_that_person(world):
    html = _browser().get(f"/contracts/{world['own']}").text
    picker = re.search(r'<select name="contact_person_id">.*?</select>', html, re.S).group(0)
    assert "Pat Freelancer" in picker and "Mara Beispiel" not in picker and "Olga Fremd" not in picker


def test_text_with_markup_is_shown_as_text_never_run(world):
    with workspace_scope(world["first"]):
        update_contract(world["contract"], world["first"], "<b>Bold</b> & co", "other",
                        "<script>alert(1)</script>\nsecond line <img src=x onerror=alert(2)>", None)
    html = _browser().get(f"/contracts/{world['contract']}").text
    assert "<script>alert(1)" not in html and "<img src=x" not in html and "<b>Bold</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;b&gt;Bold&lt;/b&gt; &amp; co" in html
    assert '<div class="contract-assignment">' in html and "second line" in html


def test_the_assignment_keeps_its_line_breaks_and_the_template_never_trusts_text(world):
    assert re.search(r"\.contract-assignment\s*\{[^}]*white-space:\s*pre-wrap", (ROOT / "gcrm/ui/static/contracts.css").read_text())
    template = (ROOT / "gcrm/ui/templates/contract_detail.html").read_text()
    assert "|safe" not in template.replace(" ", "") and "autoescape false" not in template


# --- links -------------------------------------------------------------------

def _link_ids(contract):
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM contract_links WHERE contract_id = %s ORDER BY sort_order, id", (contract,))
        return [row["id"] for row in cursor.fetchall()]


def test_links_are_added_in_order_opened_in_a_new_tab_moved_and_removed(world):
    owner = _browser()
    for label, url in (("Syllabus", "https://example.org/syllabus"), ("Slides", "http://example.org/slides"), ("Recording", "https://example.org/rec")):
        assert owner.post(f"/contracts/{world['contract']}/links", data={"label": label, "url": url}, follow_redirects=False).status_code == 303
    html = owner.get(f"/contracts/{world['contract']}").text
    assert [m for m in re.findall(r'<a href="https?://[^"]+" target="_blank" rel="noopener noreferrer">([^<]+)</a>', html)] == [
        "Syllabus", "Slides", "Recording"]
    assert len(re.findall(r'<a href="https?://', re.search(r'id="links".*?</section>', html, re.S).group(0))) == 3     # none without rel
    first, second, third = _link_ids(world["contract"])
    assert owner.post(f"/contracts/{world['contract']}/links/{third}/move", data={"direction": "up"}, follow_redirects=False).status_code == 303
    assert _link_ids(world["contract"]) == [first, third, second]
    assert owner.post(f"/contracts/{world['contract']}/links/{first}/move", data={"direction": "up"}, follow_redirects=False).status_code == 303
    assert _link_ids(world["contract"]) == [first, third, second]                  # the first cannot go up
    assert owner.post(f"/contracts/{world['contract']}/links/{third}/delete", follow_redirects=False).status_code == 303
    assert _link_ids(world["contract"]) == [first, second]


@pytest.mark.parametrize("label,url,words", [
    ("Evil", "javascript:alert(1)", "http://"), ("Evil", "data:text/html,<script>alert(1)</script>", "http://"),
    ("Evil", "ftp://example.org/a", "http://"), ("Evil", "example.org", "http://"), ("   ", "https://example.org", "label"),
    ("Long", "https://example.org/" + "a" * 2000, "2,000"),
])
def test_a_link_that_is_refused_shows_why_and_is_not_saved(world, label, url, words):
    response = _browser().post(f"/contracts/{world['contract']}/links", data={"label": label, "url": url}, follow_redirects=False)
    assert response.status_code == 400
    assert words in re.search(r'<p class="error" role="alert">(.*?)</p>', response.text, re.S).group(1)
    assert _link_ids(world["contract"]) == []
    assert "javascript:alert" not in response.text.replace("&lt;", "<").split('id="links"')[-1].split("</section>")[0]


def test_a_link_cannot_be_moved_or_removed_through_another_contract(world):
    with workspace_scope(world["first"]):
        add_link(world["contract"], world["first"], "Syllabus", "https://example.org/syllabus")
    (link,) = _link_ids(world["contract"])
    owner = _browser()
    assert owner.post(f"/contracts/{world['single']}/links/{link}/delete", follow_redirects=False).status_code == 404
    assert owner.post(f"/contracts/{world['single']}/links/{link}/move", data={"direction": "down"}, follow_redirects=False).status_code == 404
    assert _link_ids(world["contract"]) == [link]


# --- payments ----------------------------------------------------------------

def test_a_payment_is_added_to_this_contract_and_shows_in_its_money(world):
    owner = _browser()
    response = owner.post(f"/contracts/{world['single']}/payments", follow_redirects=False,
                          data={"amount_eur": "250,50", "status": "booked", "expected_on": "01.06.2027"})
    assert response.status_code == 303 and response.headers["location"] == f"/contracts/{world['single']}?open=payments"
    html = owner.get(response.headers["location"]).text
    assert eur("750.50") in html and "(2)" in html
    with workspace_scope(world["first"]):
        assert len(list_contracts(world["first"])) == 3                       # no second contract was made


@pytest.mark.parametrize("data,words", [
    ({"amount_eur": "0", "status": "booked", "expected_on": ""}, "above 0"),
    ({"amount_eur": "abc", "status": "booked", "expected_on": ""}, "above 0"),
    ({"amount_eur": "", "status": "booked", "expected_on": ""}, "above 0"),
    ({"amount_eur": "10", "status": "booked", "expected_on": "31.02.2027"}, ""),
])
def test_a_payment_that_is_refused_shows_why_and_is_not_added(world, data, words):
    response = _browser().post(f"/contracts/{world['single']}/payments", data=data, follow_redirects=False)
    assert response.status_code == 400 and words in response.text
    assert re.search(r'<details[^>]*id="payments"[^>]*\bopen\b', response.text)
    with workspace_scope(world["first"]):
        assert len(get_contract(world["single"], world["first"])["payments"]) == 1


# --- deleting ----------------------------------------------------------------

def test_deleting_a_contract_removes_it_and_its_payments_from_the_list_and_the_forecast_numbers(world):
    owner = _browser()
    before = business_revenue(world["first"])["total"]
    response = owner.post(f"/contracts/{world['contract']}/delete", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/contracts/"
    assert "Year course" not in owner.get("/contracts/").text and "Single job" in owner.get("/contracts/").text
    assert owner.get(f"/contracts/{world['contract']}").status_code == 404
    assert business_revenue(world["first"])["total"] == before - 2400
    assert owner.post(f"/contracts/{world['contract']}/delete", follow_redirects=False).status_code == 404       # not twice


def test_the_delete_button_asks_first_and_names_how_many_payments_go(world):
    html = _browser().get(f"/contracts/{world['contract']}").text
    form = re.search(r'<form method="post" action="/contracts/\d+/delete"[^>]*>', html).group(0)
    assert "data-confirm=" in form and "4 payments" in form


def test_deleting_the_last_payment_from_here_returns_to_the_list_not_to_a_missing_page(world):
    owner = _browser()
    html = owner.get(f"/contracts/{world['single']}?open=payments").text
    assert re.search(rf'/sales/\d+/delete"[^>]*>{CSRF_INPUT}\s*<input type="hidden" name="next" value="/contracts/" />', html)
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM sales WHERE contract_id = %s", (world["single"],))
        sale = cursor.fetchone()["id"]
    response = owner.post(f"/deals/{world['deal']}/sales/{sale}/delete", data={"next": "/contracts/"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/contracts/"
    assert owner.get(f"/contracts/{world['single']}").status_code == 404             # the emptied contract was retired


def test_a_sale_control_sends_the_reader_back_to_the_contract_page_with_the_payments_open(world):
    owner = _browser()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM sales WHERE contract_id = %s", (world["single"],))
        sale = cursor.fetchone()["id"]
    back = f"/contracts/{world['single']}?open=payments"
    response = owner.post(f"/deals/{world['deal']}/sales/{sale}/status", data={"status": "contracted", "next": back}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == back
    assert "Contracted" in owner.get(back).text


def test_a_multi_payment_contract_keeps_its_page_after_one_payment_goes(world):
    html = _browser().get(f"/contracts/{world['contract']}?open=payments").text
    assert re.search(rf'/sales/\d+/delete"[^>]*>{CSRF_INPUT}\s*<input type="hidden" name="next" value="/contracts/{world["contract"]}\?open=payments" />', html)


# --- the browser's proof of intent ---------------------------------------------

@pytest.mark.security_boundary
def test_a_write_without_the_session_token_is_refused_and_with_it_accepted(world):
    client = TestClient(main.app, base_url="https://testserver", follow_redirects=False)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/login").text)
    client.headers["Origin"] = "https://testserver"
    if token:
        client.headers["X-CSRF-Token"] = token.group(1)
    assert client.post("/login", data={"email": "owner@first.example", "password": PASSWORD}).status_code == 303
    good = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/settings").text)
    form = {"title": "Changed by a forged form", "kind": "other", "assignment": "", "contact_person_id": ""}
    for path, data in _writes(world["contract"]):
        client.headers.pop("X-CSRF-Token", None)
        assert client.post(path, data=data).status_code == 403, path                       # no token
        client.headers["X-CSRF-Token"] = "wrong-token"
        assert client.post(path, data=data).status_code == 403, path                       # wrong token
    assert _title(world["contract"]) == "Year course" and _link_ids(world["contract"]) == []
    client.headers["X-CSRF-Token"] = good.group(1)
    assert client.post(f"/contracts/{world['contract']}", data=form).status_code == 303   # the right token works
    assert _title(world["contract"]) == "Changed by a forged form"


# --- texts -------------------------------------------------------------------

def test_every_text_on_the_page_is_translated_in_english_and_in_german(world):
    keys = [k for k in json.load(open(ROOT / "gcrm/i18n/en.json")) if k.startswith("contractPage.")]
    german_keys = [k for k in json.load(open(ROOT / "gcrm/i18n/de.json")) if k.startswith("contractPage.")]
    assert sorted(keys) == sorted(german_keys) and keys
    owner = _browser()
    english = owner.get(f"/contracts/{world['contract']}").text
    owner.post("/settings/language", data={"ui_language": "de"})
    german = owner.get(f"/contracts/{world['contract']}").text
    for html in (english, german):
        assert not [key for key in keys if key in html], "an untranslated key shows on the page"
    for text in ("Bearbeiten", "Zahlungen", "Vertrag löschen", "Webadresse", "Alle Verträge"):
        assert text in german, text
    assert "Edit" in english and "Delete contract" in english and "Bearbeiten" not in english


def test_the_monthly_series_delete_on_this_page_does_not_pretend_to_delete_the_contract(world):
    html = _browser().get(f"/contracts/{world['contract']}?open=payments").text
    series_form = re.search(r'<form method="post" action="/deals/\d+/series/[^/]+/delete"[^>]*>', html).group(0)
    assert "Delete the whole contract" not in html and "monthly payments" in series_form          # its confirm says what goes
    assert "Delete the monthly payments" in html and html.count("Delete contract") == 1          # one real "Delete contract"
