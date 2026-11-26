"""Convert OCR bill columns to the same table format used for digital text."""

import re

from backend.documents.bill_totals import parse_inr_amount, total_field


_COLUMN_GAP = re.compile(r"\s{2,}")
_SCAN_AMOUNT = re.compile(r"(?P<minus>[-−])?\s*[₹¥%£=Xx]?\s*(?P<amount>[0-9][0-9,.]*)")
_NUMBERED_DESCRIPTION = re.compile(r"([1-9][0-9]*)\s+(.+)")
_GROSS_LABEL = re.compile(r"\b(?:gross total|subtotal|total itemized charges)\s*:", re.I)
_RATE_FIRST_HEADER = re.compile(r"\bcharge head\s+rate\s+units?\s+qty\s+line total\b", re.I)
_RATE_FIRST_ROW = re.compile(
    r"^\W*[A-Z]{2,5}[- ]?\d{2,8}\s+\W*(?P<description>.+?)\s{2,}"
    r"(?P<rate>\S+)\s+\|?\s*(?P<unit>[a-z]+)\s+\|?\s*(?P<qty>\d+)"
    r"(?:\s+[a-z]{1,2})?\s+(?P<amount>\S+)\s*\|?\s*$", re.I,
)


def _money_token(text: str) -> str | None:
    # Tesseract can misread the currency glyph. Keep every recognized digit.
    match = _SCAN_AMOUNT.fullmatch(text.strip())
    if match is None:
        return None
    token = f"{match['minus'] or ''}₹{match['amount']}"
    return token if parse_inr_amount(token, allow_deduction=True) is not None else None


def normalize_scanned_bill(text: str) -> str:
    """Preserve readable totals and canonicalize a complete aligned table."""
    totals = []
    rows = []
    header = None
    in_table = False
    complete = True
    rate_first = False
    for raw_line in text.splitlines():
        line = raw_line.replace("|", " ").strip()
        if not line:
            continue
        if line.casefold().startswith("payment mode:"):
            boundary = _GROSS_LABEL.search(line)
            line = line[boundary.start():] if boundary else ""
        field = total_field(line)
        if field is not None:
            label, _, raw_amount = line.partition(":")
            token = _money_token(raw_amount)
            if token:
                totals.append(f"{label}: {token}")
            if field == "gross" and in_table:
                # Keep the table boundary even when the gross amount is unreadable.
                rows.append(f"{label}:")
                in_table = False
            continue
        columns = _COLUMN_GAP.split(line)
        clean = [" ".join(value.casefold().split()) for value in columns]
        names = clean[1:] if clean and clean[0] == "#" else clean
        if _RATE_FIRST_HEADER.search(line):
            if header is not None:
                complete = False
            header = ["Description", "Quantity", "Unit", "Rate", "Amount"]
            rate_first = in_table = True
            continue
        if (
            len(names) == 4
            and names[:2] == ["description", "quantity"]
            and names[2] in {"rate", "unit price"}
            and names[3] == "amount"
        ):
            if header is not None:
                complete = False
            header = columns
            in_table = True
            continue
        if not in_table or not line:
            continue
        if rate_first:
            match = _RATE_FIRST_ROW.fullmatch(raw_line.strip())
            if not match:
                complete = False
                continue
            rate, amount = map(_money_token, (match["rate"], match["amount"]))
            if rate is None or amount is None:
                complete = False
                continue
            rows.extend([match["description"], match["qty"], match["unit"], rate, amount])
            continue
        if header[0] == "#":
            if len(columns) == 4:
                numbered = _NUMBERED_DESCRIPTION.fullmatch(columns[0])
                if numbered:
                    columns = [numbered[1], numbered[2], *columns[1:]]
            expected_columns = 5
        else:
            expected_columns = 4
        if len(columns) != expected_columns:
            complete = False
            continue
        rate, amount = map(_money_token, columns[-2:])
        if rate is None or amount is None:
            complete = False
            continue
        rows.extend([*columns[:-2], rate, amount])

    if header and rows and complete and not in_table:
        boundary = rows.pop()
        # A readable gross line doubles as the table boundary. Place it first.
        gross = next((line for line in totals if total_field(line) == "gross"), boundary)
        if gross in totals:
            totals.remove(gross)
        return "\n".join([*header, *rows, gross, *totals])
    return "\n".join(totals)
