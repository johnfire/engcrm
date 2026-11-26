from gcrm.income_calculator.estimate import EstimateInputs, calculate_estimates
from gcrm.income_calculator.income_2026 import income_tax_cents, solidarity_cents


def test_income_tax_2026_progressive_boundaries():
    assert income_tax_cents(1_234_800) == 0
    assert income_tax_cents(1_780_000) == 103_500
    assert income_tax_cents(5_000_000) == 1_054_800
    assert income_tax_cents(30_000_000) == 11_552_900


def test_solidarity_surcharge_has_threshold_and_mitigation_zone():
    assert solidarity_cents(2_035_000) == 0
    assert solidarity_cents(2_035_100) == 11
    assert solidarity_cents(3_000_000) == 114_835


def test_estimate_keeps_cash_costs_tax_deductions_and_payments_distinct():
    inputs = EstimateInputs(
        consulting_cents=7_500_000,
        education_cents=0,
        expense_cash_cents=1_000_000,
        business_deduction_cents=800_000,
        personal_cash_cents=600_000,
        personal_deduction_cents=400_000,
        paid_tax_cents=100_000,
        months_remaining=4,
        church_rate_percent=8,
    )
    scenarios = calculate_estimates(inputs)
    regular = scenarios[1]
    assert regular.revenue_cents == 6_302_521
    assert regular.taxable_income_cents == 5_102_521
    assert regular.disposable_cents == 7_500_000 - 1_600_000 - 1_197_479 - regular.total_tax_cents
    assert regular.remaining_tax_cents == max(0, regular.total_tax_cents - 100_000)
    assert regular.monthly_cents == regular.disposable_cents // 4


def test_startup_grant_increases_cash_without_changing_tax_or_vat():
    without_grant = EstimateInputs(
        consulting_cents=7_500_000,
        education_cents=0,
        startup_grant_cents=0,
        expense_cash_cents=1_000_000,
        business_deduction_cents=800_000,
        personal_cash_cents=600_000,
        personal_deduction_cents=400_000,
        paid_tax_cents=0,
        months_remaining=12,
        church_rate_percent=8,
    )
    with_grant = EstimateInputs(
        consulting_cents=7_500_000,
        education_cents=0,
        startup_grant_cents=1_000_000,
        expense_cash_cents=1_000_000,
        business_deduction_cents=800_000,
        personal_cash_cents=600_000,
        personal_deduction_cents=400_000,
        paid_tax_cents=0,
        months_remaining=12,
        church_rate_percent=8,
    )

    for baseline, grant in zip(
        calculate_estimates(without_grant), calculate_estimates(with_grant), strict=True
    ):
        assert grant.startup_grant_cents == 1_000_000
        assert grant.receipts_cents == baseline.receipts_cents
        assert grant.output_vat_cents == baseline.output_vat_cents
        assert grant.taxable_income_cents == baseline.taxable_income_cents
        assert grant.total_tax_cents == baseline.total_tax_cents
        assert grant.disposable_cents == baseline.disposable_cents + 1_000_000
