"""The form boundary: text typed in euros becomes integer cents for the engine.

Decimal input is accepted here and nowhere else; the engine only sees cents.
"""
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, field_validator

from gcrm.income_calculator.estimate import EstimateInputs
from gcrm.income_calculator.vat import AmountBasis

MAX_EUROS = 10_000_000
MONEY_FIELDS = (
    "consulting", "education", "startup_grant", "expenses", "business_deduction",
    "health_costs", "health_deduction", "pension_costs", "pension_deduction",
    "medical_costs", "medical_deduction", "disability_allowance", "paid_tax",
)


def _money() -> Decimal:
    return Field(default=Decimal(0), ge=0, le=MAX_EUROS, decimal_places=2)


def cents(euros: Decimal) -> int:
    return int(euros * 100)


class IncomeCalculatorForm(BaseModel):
    consulting: Decimal = _money()
    education: Decimal = _money()
    startup_grant: Decimal = _money()
    expenses: Decimal = _money()
    business_deduction: Decimal = _money()
    health_costs: Decimal = _money()
    health_deduction: Decimal = _money()
    pension_costs: Decimal = _money()
    pension_deduction: Decimal = _money()
    medical_costs: Decimal = _money()
    medical_deduction: Decimal = _money()
    disability_allowance: Decimal = _money()
    paid_tax: Decimal = _money()
    months_remaining: int = Field(default=12, ge=1, le=12)
    church_rate: int = Field(default=0, ge=0, le=9)
    amount_basis: AmountBasis = AmountBasis.GROSS

    @field_validator(*MONEY_FIELDS, mode="before")
    @classmethod
    def normalize_amount(cls, amount: object) -> object:
        """Blank is zero; a comma is a decimal point; anything else is left for validation."""
        if isinstance(amount, str):
            try:
                return Decimal(amount.strip().replace(",", ".")) if amount.strip() else Decimal(0)
            except InvalidOperation:
                return amount
        return amount

    @field_validator("church_rate")
    @classmethod
    def church_rate_is_offered(cls, rate: int) -> int:
        if rate not in (0, 8, 9):
            raise ValueError("church rate must be 0, 8 or 9")
        return rate

    def to_inputs(self) -> EstimateInputs:
        return EstimateInputs(
            consulting_cents=cents(self.consulting),
            education_cents=cents(self.education),
            startup_grant_cents=cents(self.startup_grant),
            expense_cash_cents=cents(self.expenses),
            business_deduction_cents=cents(self.business_deduction),
            personal_cash_cents=cents(self.health_costs + self.pension_costs + self.medical_costs),
            personal_deduction_cents=cents(
                self.health_deduction + self.pension_deduction
                + self.medical_deduction + self.disability_allowance
            ),
            paid_tax_cents=cents(self.paid_tax),
            months_remaining=self.months_remaining,
            church_rate_percent=self.church_rate,
            amount_basis=self.amount_basis,
        )
