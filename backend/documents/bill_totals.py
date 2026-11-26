"""Read and reconcile common printed bill totals."""

import re
from dataclasses import dataclass
from decimal import Decimal


_TOTAL_LABELS = {
    "gross charges": "gross",
    "gross hospital charges": "gross",
    "total billed charges": "gross",
    "gross bill amount": "gross",
    "gross bill total": "gross",
    "gross amount": "gross",
    "pharmacy gross": "gross",
    "hospital discount": "discount",
    "institutional rebate": "discount",
    "pharmacy discount": "discount",
    "net bill amount": "net",
    "net hospital bill": "net",
    "net payable": "net",
    "net payable bill": "net",
    "net tax invoice amount": "net",
    "advance deposit paid": "advance",
    "deposit received": "advance",
    "balance due": "balance",
    "hospital balance due": "balance",
    "closing balance due": "balance",
    "gross total": "gross",
    "subtotal": "gross",
    "total itemized charges": "gross",
    "discount": "discount",
    "concession": "discount",
    "package adjustment": "discount",
    "net bill": "net",
    "net amount": "net",
    "invoice total": "net",
    "advance paid": "advance",
    "advance": "advance",
    "balance payable": "balance",
    "amount due": "balance",
}
_AMOUNT = re.compile(
    r"(?P<minus>[-−])?\s*(?:₹|INR|Rs\.?)\s*"
    r"(?P<number>(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3})"
    r"(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BillTotal:
    amount: Decimal
    page: int


@dataclass(frozen=True)
class BillTotals:
    gross: BillTotal | None = None
    discount: BillTotal | None = None
    net: BillTotal | None = None
    advance: BillTotal | None = None
    balance: BillTotal | None = None

    def reconciliation_checks(self) -> list[tuple[bool, str]]:
        checks = []
        if self.gross and self.discount and self.net:
            checks.append((
                self.gross.amount - self.discount.amount == self.net.amount,
                "Gross charges minus discount match the printed net charges.",
            ))
        if self.net and self.advance and self.balance:
            checks.append((
                self.net.amount - self.advance.amount == self.balance.amount,
                "Net charges minus the advance match the printed balance due.",
            ))
        return checks


def total_field(line: str) -> str | None:
    label, separator, _ = line.partition(":")
    return _TOTAL_LABELS.get(" ".join(label.casefold().split())) if separator else None


def parse_inr_amount(text: str, *, allow_deduction: bool = False) -> Decimal | None:
    """Read an INR amount, treating a labeled deduction as a positive magnitude."""
    number = _AMOUNT.fullmatch(text.strip())
    if number is None or (number["minus"] and not allow_deduction):
        return None
    return Decimal(number["number"].replace(",", ""))


def find_bill_totals(pages: list[str]) -> BillTotals | None:
    """Return one amount per expected label, preserving its original PDF page."""
    values: dict[str, BillTotal] = {}
    for page_number, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            field = total_field(line)
            if field is None:
                continue
            amount_text = line.partition(":")[2].strip()
            if not amount_text and index + 1 < len(lines):
                amount_text = lines[index + 1]
            amount = parse_inr_amount(amount_text, allow_deduction=field in {"discount", "advance"})
            if field in values or amount is None:
                return None
            values[field] = BillTotal(amount, page_number)

    return BillTotals(**values) if values else None
