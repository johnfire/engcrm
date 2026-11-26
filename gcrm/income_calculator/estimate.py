"""Annual illustrative estimates; no cash-timing or official assessment."""

from dataclasses import dataclass

from gcrm.income_calculator.income_2026 import income_tax_cents, solidarity_cents
from gcrm.income_calculator.vat import (
    AmountBasis,
    Sale,
    VatProfile,
    VatTreatment,
    calculate_vat_scenarios,
)


@dataclass(frozen=True)
class EstimateInputs:
    consulting_cents: int
    education_cents: int
    expense_cash_cents: int
    business_deduction_cents: int
    personal_cash_cents: int
    personal_deduction_cents: int
    paid_tax_cents: int
    months_remaining: int
    church_rate_percent: int
    startup_grant_cents: int = 0
    amount_basis: AmountBasis = AmountBasis.GROSS


@dataclass(frozen=True)
class Estimate:
    label: str
    receipts_cents: int
    startup_grant_cents: int
    output_vat_cents: int
    revenue_cents: int
    profit_cents: int
    taxable_income_cents: int
    income_tax_cents: int
    solidarity_cents: int
    church_tax_cents: int
    total_tax_cents: int
    remaining_tax_cents: int
    disposable_cents: int
    monthly_cents: int


def calculate_estimates(inputs: EstimateInputs) -> tuple[Estimate, ...]:
    sales = [
        Sale(inputs.education_cents, VatTreatment.EDUCATION_EXEMPT),
        Sale(inputs.consulting_cents, basis=inputs.amount_basis),
    ]
    scenarios = calculate_vat_scenarios(sales, VatProfile.UNKNOWN, 0)
    estimates = []
    for scenario in scenarios:
        profit = scenario.revenue_cents - inputs.business_deduction_cents
        taxable = max(0, profit - inputs.personal_deduction_cents)
        income_tax = income_tax_cents(taxable)
        solidarity = solidarity_cents(income_tax)
        church_tax = income_tax * inputs.church_rate_percent // 100
        total_tax = income_tax + solidarity + church_tax
        disposable = (
            scenario.receipts_cents
            + inputs.startup_grant_cents
            - scenario.output_vat_cents
            - inputs.expense_cash_cents
            - inputs.personal_cash_cents
            - total_tax
        )
        estimates.append(
            Estimate(
                label="Kleinunternehmer"
                if scenario.profile == VatProfile.KLEINUNTERNEHMER
                else "Regular VAT",
                receipts_cents=scenario.receipts_cents,
                startup_grant_cents=inputs.startup_grant_cents,
                output_vat_cents=scenario.output_vat_cents,
                revenue_cents=scenario.revenue_cents,
                profit_cents=profit,
                taxable_income_cents=taxable,
                income_tax_cents=income_tax,
                solidarity_cents=solidarity,
                church_tax_cents=church_tax,
                total_tax_cents=total_tax,
                remaining_tax_cents=max(0, total_tax - inputs.paid_tax_cents),
                disposable_cents=disposable,
                monthly_cents=disposable // inputs.months_remaining,
            )
        )
    return tuple(estimates)
