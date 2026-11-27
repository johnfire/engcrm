"""The switch between typed income and the Forecast's income."""
import re
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.auth import require_login
from gcrm.api.routers.income_calculator import account_id
from gcrm.tools.forecast_income import ForecastIncome, IncomeLine

client = TestClient(main.app)
ROUTER = "gcrm.api.routers.income_calculator"
D = Decimal

INCOME = ForecastIncome(
    consulting=D("10000"), teaching=D("20000"), possible=D("0"), possible_as="consulting",
    lines=(IncomeLine(1, "Evening course", "VHS Musterstadt", "teaching_course", D("20000"), 4),
           IncomeLine(2, "Advice", "Example GmbH", "consulting", D("10000"), 1)),
    unclassified=(), undated_total=D("0"), undated_count=0,
)


@pytest.fixture(autouse=True)
def signed_in():
    main.app.dependency_overrides[require_login] = lambda: "admin"
    main.app.dependency_overrides[account_id] = lambda: 7
    with patch(f"{ROUTER}.session_workspace_id", return_value=1), \
         patch(f"{ROUTER}.load_inputs", return_value=None) as load, patch(f"{ROUTER}.save_inputs") as save:
        yield load, save
    main.app.dependency_overrides.pop(require_login, None)
    main.app.dependency_overrides.pop(account_id, None)


@pytest.fixture
def forecast():
    with patch(f"{ROUTER}.get_forecast_income", return_value=INCOME) as lookup:
        yield lookup


def receipts(page):
    return re.findall(r"<dt>Customer receipts</dt><dd>([^<]+)</dd>", page)


def post(**data):
    return client.post("/income-calculator", data=data)


def test_manual_mode_never_asks_the_forecast(forecast):
    page = post(consulting="100", income_source="manual").text
    forecast.assert_not_called()
    assert receipts(page)[0] == "100 €"


def test_forecast_mode_uses_the_forecast_income_instead_of_the_typed_one(forecast, signed_in):
    _, save = signed_in
    page = post(consulting="999999", education="5", income_source="forecast", startup_grant="1000").text
    assert receipts(page) == ["30.000 €", "30.000 €"]
    # What was typed is kept, on the page and in storage, for switching back.
    assert 'value="999999"' in page
    assert save.call_args.args[1]["consulting"] == "999999"
    assert save.call_args.args[1]["income_source"] == "forecast"


def test_forecast_mode_lists_what_it_counted(forecast):
    page = post(income_source="forecast").text
    assert "Evening course" in page and "VHS Musterstadt" in page and "Example GmbH" in page


def test_the_choices_reach_the_forecast_lookup(forecast):
    post(income_source="forecast")
    assert forecast.call_args.kwargs == {"include_expected": False, "include_possible": False,
                                         "possible_as": "consulting"}
    assert forecast.call_args.args == (1, 2027)
    post(income_source="forecast", include_expected="on", include_possible="on", possible_as="teaching")
    assert forecast.call_args.kwargs == {"include_expected": True, "include_possible": True,
                                         "possible_as": "teaching"}


def test_the_amount_basis_applies_to_the_forecast_consulting(forecast):
    page = post(income_source="forecast", amount_basis="net_fee").text
    vat = re.findall(r"<dt>Estimated output VAT</dt><dd>([^<]+)</dd>", page)
    assert vat == ["0 €", "1.900 €"]


def test_unclassified_and_undated_money_is_pointed_out(forecast):
    forecast.return_value = ForecastIncome(
        consulting=D("0"), teaching=D("0"), possible=D("0"), possible_as="consulting", lines=(),
        unclassified=(IncomeLine(9, "Mystery job", "Example GmbH", "other", D("500"), 1),),
        undated_total=D("700"), undated_count=2)
    page = post(income_source="forecast").text
    assert "Mystery job" in page and "500 €" in page
    assert "700 €" in page and "no due day" in page.lower()


def test_a_forecast_failure_never_falls_back_to_the_typed_numbers(forecast):
    forecast.side_effect = RuntimeError("database away")
    response = post(consulting="100", income_source="forecast")
    assert response.status_code == 200
    assert "could not be read from the Forecast" in response.text
    assert "income-calculator-hero" not in response.text


def test_a_saved_forecast_choice_is_calculated_from_todays_forecast(forecast, signed_in):
    load, _ = signed_in
    load.return_value = {"income_source": "forecast", "include_expected": True}
    page = client.get("/income-calculator").text
    assert receipts(page) == ["30.000 €", "30.000 €"]
    assert forecast.call_args.kwargs["include_expected"] is True


@pytest.mark.parametrize("bad", [{"income_source": "somewhere"}, {"possible_as": "free"}])
def test_unknown_choices_are_refused(forecast, bad):
    assert post(**bad).status_code == 422
