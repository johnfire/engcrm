"""Single-assessment tariff in force from 2026 (§32a EStG), excluding special tax circumstances."""

from decimal import ROUND_DOWN, Decimal


def income_tax_cents(taxable_cents: int) -> int:
    income = Decimal(max(0, taxable_cents) // 100)
    if income <= 12348:
        tax = Decimal(0)
    elif income <= 17799:
        variable = (income - 12348) / 10000
        tax = (Decimal("914.51") * variable + 1400) * variable
    elif income <= 69878:
        variable = (income - 17799) / 10000
        tax = (Decimal("173.10") * variable + 2397) * variable + Decimal("1034.87")
    elif income <= 277825:
        tax = Decimal("0.42") * income - Decimal("11135.63")
    else:
        tax = Decimal("0.45") * income - Decimal("19470.38")
    return int(tax.to_integral_value(rounding=ROUND_DOWN)) * 100


def solidarity_cents(income_tax: int) -> int:
    excess = max(0, income_tax - 2_035_000)
    return int(min(Decimal(income_tax) * Decimal("0.055"), Decimal(excess) * Decimal("0.119")))
