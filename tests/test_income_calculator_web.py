"""The income calculator page: access, parsing, rendering, and that it keeps nothing."""
import re

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_login

client = TestClient(main.app)

FIELDS = [
    "consulting", "amount_basis", "education", "startup_grant", "expenses", "business_deduction",
    "health_costs", "health_deduction", "pension_costs", "pension_deduction", "medical_costs",
    "medical_deduction", "disability_allowance", "paid_tax", "months_remaining", "church_rate",
]


@pytest.fixture
def signed_in():
    main.app.dependency_overrides[require_login] = lambda: "spectator"
    yield
    main.app.dependency_overrides.pop(require_login, None)


def page(language="en"):
    return client.get("/income-calculator", cookies={}).text


def post(**data):
    return client.post("/income-calculator", data=data)


def hero_amounts(html):
    return re.findall(r'income-calculator-hero">([^<]+)<', html)


def row(html, label):
    return re.findall(rf"<dt>{re.escape(label)}</dt><dd>([^<]+)</dd>", html)


def test_anonymous_visitor_is_sent_to_login():
    response = client.get("/income-calculator", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "/login"
    assert client.post("/income-calculator", data={"consulting": "1"}, follow_redirects=False).status_code == 307


def test_anyone_signed_in_can_open_it_and_sees_every_field(signed_in):
    response = client.get("/income-calculator")
    assert response.status_code == 200
    for name in FIELDS:
        assert f'name="{name}"' in response.text
    assert "2026" in response.text and "not tax advice" in response.text


def test_valid_input_shows_both_vat_scenarios(signed_in):
    html = post(consulting="75000", amount_basis="gross_customer_total").text
    assert "Kleinunternehmer" in html and "Regular VAT" in html
    assert row(html, "Revenue excluding VAT") == ["75.000 €", "63.025,21 €"]
    assert row(html, "Estimated output VAT") == ["0 €", "11.974,79 €"]


def test_comma_and_point_decimals_give_the_same_result(signed_in):
    assert hero_amounts(post(consulting="1234,50").text) == hero_amounts(post(consulting="1234.50").text)


@pytest.mark.parametrize("bad", ["-10", "abc", "10.123", "10000000.01"])
def test_bad_money_is_refused_and_values_survive(signed_in, bad):
    response = post(consulting=bad, expenses="321", months_remaining="6", church_rate="8")
    assert response.status_code == 422
    assert "Please check your figures" in response.text
    assert 'value="321"' in response.text and 'value="6"' in response.text
    assert 'name="consulting"' in response.text and f'value="{bad}"' in response.text
    assert "Traceback" not in response.text and "ValidationError" not in response.text


@pytest.mark.parametrize("months", ["0", "13", "x"])
def test_months_must_be_one_to_twelve(signed_in, months):
    assert post(consulting="1000", months_remaining=months).status_code == 422


def test_church_rate_must_be_offered(signed_in):
    assert post(church_rate="5").status_code == 422


def euros(text):
    """'53.634,34 €' -> 5363434 cents."""
    whole, _, cents = text.removesuffix(" €").replace(".", "").partition(",")
    return int(whole) * 100 + int((cents or "0").ljust(2, "0"))


def remainders(html):
    return [euros(amount) for amount in hero_amounts(html)]


def test_medical_cash_cost_reduces_cash_by_exactly_that_amount(signed_in):
    base = post(consulting="75000").text
    cash_only = post(consulting="75000", medical_costs="1000").text
    assert row(cash_only, "Estimated taxable income") == row(base, "Estimated taxable income")
    assert row(cash_only, "Estimated total tax") == row(base, "Estimated total tax")
    assert remainders(cash_only) == [cash - 100_000 for cash in remainders(base)]


def test_deductions_cut_taxable_income_and_the_allowance_is_never_cash(signed_in):
    base = post(consulting="75000").text
    html = post(consulting="75000", medical_costs="1000", medical_deduction="200", disability_allowance="2120").text
    assert row(base, "Estimated taxable income")[1] == "63.025,21 €"
    assert row(html, "Estimated taxable income")[1] == "60.705,21 €"
    allowance_only = post(consulting="75000", disability_allowance="2120").text
    assert row(allowance_only, "Estimated taxable income")[0] == "72.880 €"
    # The allowance only saves tax, so the remainder can rise but never fall.
    assert all(new >= old for new, old in zip(remainders(allowance_only), remainders(base)))
    assert remainders(allowance_only) != remainders(base)


def test_tax_already_paid_changes_remaining_tax_but_not_the_remainder(signed_in):
    base = post(consulting="75000", church_rate="8").text
    paid = post(consulting="75000", church_rate="8", paid_tax="1000").text
    assert hero_amounts(paid) == hero_amounts(base)
    assert row(paid, "Tax less amount paid") != row(base, "Tax less amount paid")


def test_months_divide_the_full_annual_remainder(signed_in):
    html = post(startup_grant="12000", months_remaining="4").text
    assert hero_amounts(html) == ["12.000 €", "12.000 €"]
    assert "3.000 € / selected month" in html


def test_grant_only_case_is_cash_only(signed_in):
    html = post(startup_grant="10000", months_remaining="12").text
    assert row(html, "Customer receipts") == ["0 €", "0 €"]
    assert row(html, "Tax-free Gründungszuschuss") == ["10.000 €", "10.000 €"]
    assert row(html, "Estimated taxable income") == ["0 €", "0 €"]
    assert row(html, "Estimated total tax") == ["0 €", "0 €"]
    assert hero_amounts(html) == ["10.000 €", "10.000 €"]


def test_grant_changes_only_the_cash_remainder(signed_in):
    base = post(consulting="75000", expenses="1000", business_deduction="800").text
    grant = post(consulting="75000", expenses="1000", business_deduction="800", startup_grant="10000").text
    for label in ("Customer receipts", "Estimated output VAT", "Revenue excluding VAT", "Business profit",
                  "Estimated taxable income", "Estimated total tax"):
        assert row(grant, label) == row(base, label)
    assert hero_amounts(base) != hero_amounts(grant)


def test_response_is_private_and_carries_a_csrf_token(signed_in):
    response = client.get("/income-calculator")
    assert response.headers["cache-control"] == "private, no-store"
    assert 'name="csrf_token"' in response.text
    assert "script-src" in response.headers["content-security-policy"]


def test_figures_are_never_put_in_a_url_or_redirect(signed_in):
    response = client.post("/income-calculator", data={"consulting": "98765"}, follow_redirects=False)
    assert response.status_code == 200 and "location" not in response.headers


@pytest.mark.security_boundary
def test_post_without_browser_proof_is_rejected(signed_in):
    response = client.post("/income-calculator", data={"consulting": "1000"})
    assert response.status_code in (400, 403)


def test_german_page_is_translated(signed_in):
    de = TestClient(main.app)
    de.get("/login?lang=de")
    html = de.post("/income-calculator", data={"consulting": "75000"}).text
    assert "Einkommensrechner" in html and "Regelbesteuerung" in html and "Jahresrest" in html
    assert "Calculate estimate" not in html


def test_forecast_links_to_the_calculator():
    from pathlib import Path
    html = (Path(main.__file__).parent.parent / "ui" / "templates" / "forecast.html").read_text()
    assert 'href="/income-calculator"' in html
