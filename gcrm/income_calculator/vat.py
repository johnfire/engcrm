"""Narrow, explicit 2026 VAT scenarios; this does not determine legal status."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class AmountBasis(StrEnum):
    GROSS = "gross_customer_total"
    NET = "net_fee"


class VatProfile(StrEnum):
    UNKNOWN = "unknown"
    KLEINUNTERNEHMER = "kleinunternehmer"
    REGULAR = "regular_vat"


class VatTreatment(StrEnum):
    TAXABLE = "taxable_19"
    EDUCATION_EXEMPT = "education_exempt_4_21"


PRIOR_YEAR_LIMIT_CENTS = 2_500_000
CURRENT_YEAR_LIMIT_CENTS = 10_000_000
VAT_FACTOR = Decimal("1.19")
RULE_VERSION = "2026-vat-initial"


@dataclass(frozen=True)
class Sale:
    amount_cents: int
    treatment: VatTreatment = VatTreatment.TAXABLE
    basis: AmountBasis = AmountBasis.GROSS

    def __post_init__(self) -> None:
        if type(self.amount_cents) is not int or self.amount_cents < 0:
            raise ValueError("amount_cents must be a non-negative integer")
        if not isinstance(self.treatment, VatTreatment) or not isinstance(self.basis, AmountBasis):
            raise TypeError("sale requires an explicit treatment and amount basis")


@dataclass(frozen=True)
class SaleVat:
    receipts_cents: int
    revenue_cents: int
    output_vat_cents: int
    taxable_under_regular_vat: bool


@dataclass(frozen=True)
class VatScenario:
    profile: VatProfile
    unresolved_status: bool
    kleinunternehmer_eligible: bool
    receipts_cents: int
    revenue_cents: int
    output_vat_cents: int
    section_19_turnover_cents: int
    sale_results: tuple[SaleVat, ...]
    rule_version: str = RULE_VERSION


def _round_cents(amount: Decimal) -> int:
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _calculate_sale(sale: Sale, is_taxable: bool) -> SaleVat:
    if not is_taxable:
        return SaleVat(sale.amount_cents, sale.amount_cents, 0, False)
    amount = Decimal(sale.amount_cents)
    if sale.basis == AmountBasis.GROSS:
        revenue = _round_cents(amount / VAT_FACTOR)
        return SaleVat(sale.amount_cents, revenue, sale.amount_cents - revenue, True)
    receipts = _round_cents(amount * VAT_FACTOR)
    return SaleVat(receipts, sale.amount_cents, receipts - sale.amount_cents, True)


def _calculate_scenario(
    sales: list[Sale], profile: VatProfile, prior_turnover: int, unresolved: bool
) -> VatScenario:
    eligible = prior_turnover <= PRIOR_YEAR_LIMIT_CENTS
    turnover = 0
    sale_results = []
    crossed_limit = False
    for sale in sales:
        is_relevant = sale.treatment == VatTreatment.TAXABLE
        if is_relevant:
            turnover += sale.amount_cents
            crossed_limit = crossed_limit or turnover > CURRENT_YEAR_LIMIT_CENTS
        is_taxable = is_relevant and (
            profile == VatProfile.REGULAR or not eligible or crossed_limit
        )
        sale_results.append(_calculate_sale(sale, is_taxable))
    return VatScenario(
        profile=profile,
        unresolved_status=unresolved,
        kleinunternehmer_eligible=eligible,
        receipts_cents=sum(sale.receipts_cents for sale in sale_results),
        revenue_cents=sum(sale.revenue_cents for sale in sale_results),
        output_vat_cents=sum(sale.output_vat_cents for sale in sale_results),
        section_19_turnover_cents=turnover,
        sale_results=tuple(sale_results),
    )


def calculate_vat_scenarios(
    sales: list[Sale], profile: VatProfile, prior_year_turnover_cents: int
) -> tuple[VatScenario, ...]:
    """Process sales in chronological order using their entered amounts as turnover.

    Turnover measurement and ambiguous treatments require adviser confirmation.
    """
    if type(prior_year_turnover_cents) is not int or prior_year_turnover_cents < 0:
        raise ValueError("prior-year turnover must be non-negative integer cents")
    if not isinstance(profile, VatProfile):
        raise TypeError("profile must be an explicit VAT profile")
    profiles = (
        (VatProfile.KLEINUNTERNEHMER, VatProfile.REGULAR)
        if profile == VatProfile.UNKNOWN
        else (profile,)
    )
    return tuple(
        _calculate_scenario(
            sales, selected, prior_year_turnover_cents, profile == VatProfile.UNKNOWN
        )
        for selected in profiles
    )
