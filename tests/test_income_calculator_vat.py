from decimal import Decimal

import pytest

from gcrm.income_calculator.vat import (
    AmountBasis,
    Sale,
    VatProfile,
    VatTreatment,
    calculate_vat_scenarios,
)


def sale(amount_cents, treatment=VatTreatment.TAXABLE, basis=AmountBasis.GROSS):
    return Sale(amount_cents=amount_cents, treatment=treatment, basis=basis)


def test_gross_sale_is_split_under_regular_vat():
    scenario = calculate_vat_scenarios([sale(7_500_000)], VatProfile.REGULAR, 0)[0]
    assert scenario.receipts_cents == 7_500_000
    assert scenario.revenue_cents == 6_302_521
    assert scenario.output_vat_cents == 1_197_479


def test_kleinunternehmer_does_not_split_gross_sale():
    scenario = calculate_vat_scenarios([sale(7_500_000)], VatProfile.KLEINUNTERNEHMER, 0)[0]
    assert scenario.revenue_cents == 7_500_000
    assert scenario.output_vat_cents == 0


def test_unknown_profile_returns_two_labeled_scenarios():
    scenarios = calculate_vat_scenarios([sale(7_500_000)], VatProfile.UNKNOWN, 0)
    assert [scenario.profile for scenario in scenarios] == [
        VatProfile.KLEINUNTERNEHMER,
        VatProfile.REGULAR,
    ]
    assert all(scenario.unresolved_status for scenario in scenarios)


def test_educational_receipts_are_excluded_from_relevant_turnover():
    sales = [sale(3_750_000, VatTreatment.EDUCATION_EXEMPT), sale(3_750_000)]
    scenarios = calculate_vat_scenarios(sales, VatProfile.UNKNOWN, 0)
    assert all(scenario.section_19_turnover_cents == 3_750_000 for scenario in scenarios)
    assert scenarios[1].output_vat_cents == 598_739


def test_prior_year_turnover_above_limit_disallows_kleinunternehmer():
    scenario = calculate_vat_scenarios([sale(100_000)], VatProfile.KLEINUNTERNEHMER, 2_500_001)[0]
    assert scenario.output_vat_cents > 0
    assert not scenario.kleinunternehmer_eligible


def test_limit_is_inclusive_and_crossing_sale_is_taxable_in_full():
    sales = [sale(8_000_000), sale(2_000_000), sale(1)]
    scenario = calculate_vat_scenarios(sales, VatProfile.KLEINUNTERNEHMER, 0)[0]
    assert scenario.sale_results[1].output_vat_cents == 0
    assert scenario.sale_results[2].taxable_under_regular_vat


def test_entire_crossing_sale_is_taxable():
    scenario = calculate_vat_scenarios(
        [sale(8_000_000), sale(4_000_000)], VatProfile.KLEINUNTERNEHMER, 0
    )[0]
    assert scenario.sale_results[1].output_vat_cents == 638_655


def test_net_fee_adds_vat_in_regular_scenario():
    scenario = calculate_vat_scenarios(
        [sale(100_000, basis=AmountBasis.NET)], VatProfile.REGULAR, 0
    )[0]
    assert scenario.receipts_cents == 119_000
    assert scenario.revenue_cents == 100_000
    assert scenario.output_vat_cents == 19_000


def test_invalid_money_is_rejected():
    with pytest.raises(ValueError):
        sale(-1)
    with pytest.raises((TypeError, ValueError)):
        sale(Decimal("1.1"))
