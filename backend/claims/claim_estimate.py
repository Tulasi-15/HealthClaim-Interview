"""Calculate a reimbursement estimate from reviewed bill and policy inputs."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from backend.documents.bill_items import BillItem


_PAISA = Decimal("0.01")
_COPAYMENT = re.compile(
    r"\b9\.5\.?\s+co[ -]?payment\s+"
    r"(?P<excerpt>each and every claim under the policy shall be subject to a co[ -]?payment of "
    r"(?P<percent>[0-9]+(?:\.[0-9]+)?)\s*%\s+applicable to claim "
    r"amount admissible and payable as per the terms and conditions of the policy\.)",
    re.I,
)


@dataclass(frozen=True)
class CopaymentRule:
    percent: Decimal
    page: int | None
    excerpt: str


@dataclass(frozen=True)
class ReviewedDeduction:
    item: BillItem
    amount: Decimal
    reason: str


@dataclass(frozen=True)
class ClaimEstimate:
    net_bill: Decimal
    deductions: tuple[ReviewedDeduction, ...]
    before_cover_limit: Decimal
    cover_limit_deduction: Decimal
    admissible_amount: Decimal
    copayment: Decimal
    payable: Decimal


def find_copayment_rule(pages: list[str]) -> CopaymentRule | None:
    """Read the verified admissible-amount formula in the supported policy wording."""
    matches = []
    for page, text in enumerate(pages, start=1):
        for match in _COPAYMENT.finditer(" ".join(text.split())):
            percent = Decimal(match["percent"])
            if not Decimal(0) <= percent <= Decimal(100):
                return None
            matches.append(CopaymentRule(percent, page, match["excerpt"]))
    return matches[0] if len(matches) == 1 else None


def estimate_claim(
    net_bill: Decimal,
    remaining_cover: Decimal,
    deductions: tuple[ReviewedDeduction, ...],
    rule: CopaymentRule,
) -> ClaimEstimate:
    if not all(value.is_finite() and value >= 0 for value in (net_bill, remaining_cover)):
        raise ValueError("Net bill and remaining cover must be valid nonnegative amounts.")
    if any(value != value.quantize(_PAISA) for value in (net_bill, remaining_cover)):
        raise ValueError("Use at most two decimal places for bill and cover amounts.")
    if not rule.percent.is_finite() or not Decimal(0) <= rule.percent <= Decimal(100):
        raise ValueError("The co-payment rate must be between 0% and 100%.")
    seen_rows = set()
    for deduction in deductions:
        row = (deduction.item.page, deduction.item.number)
        if row in seen_rows:
            raise ValueError("Review each bill row once to avoid duplicate deductions.")
        seen_rows.add(row)
        if not deduction.amount.is_finite() or not Decimal(0) < deduction.amount <= deduction.item.amount:
            raise ValueError(f"The deduction for row {deduction.item.number} must fit within its printed charge.")
        if deduction.amount != deduction.amount.quantize(_PAISA):
            raise ValueError(f"Use at most two decimal places for the deduction on row {deduction.item.number}.")
        if not deduction.reason.strip():
            raise ValueError(f"Provide a reason and source for the deduction on row {deduction.item.number}.")

    before_cover_limit = net_bill - sum((deduction.amount for deduction in deductions), Decimal(0))
    if before_cover_limit < 0:
        raise ValueError("Total reviewed deductions exceed the net bill.")
    admissible = min(before_cover_limit, remaining_cover)
    copayment = (admissible * rule.percent / 100).quantize(_PAISA, rounding=ROUND_HALF_UP)
    return ClaimEstimate(
        net_bill, deductions, before_cover_limit, before_cover_limit - admissible,
        admissible, copayment, admissible - copayment,
    )
