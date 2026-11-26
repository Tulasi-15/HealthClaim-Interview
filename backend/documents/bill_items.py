"""Read expense rows from supported digital bill tables."""

import re
from dataclasses import dataclass
from decimal import Decimal

from backend.documents.bill_totals import parse_inr_amount, total_field

_HEADER = re.compile(r"(?:description|particulars) (?:quantity|qty\.?) (?:rate|unit price) amount")
_SERIAL_HEADER = re.compile(r"(?:s\.?\s*no\.?|#)", re.I)
_UNIT_HEADER = re.compile(
    r"(?:description|(?:service / )?charge description|medicine / supply description|expense item)"
    r" (?:quantity|qty\.?) unit (?:rate|unit rate|unit price) (?:line )?amount"
)
_UNIT_SERIAL = re.compile(r"(?:line|#|s\.?\s*no\.?)", re.I)
_TABLE_FOOTER = re.compile(r"^(?:bill summary|(?:invoice|bill) (?:no|ref)\s*:)", re.I)
_QUANTITY = re.compile(r"(?P<count>[1-9][0-9]*)(?:\s+(?P<unit>days?))?", re.IGNORECASE)
_ROOM = re.compile(r"(?:(?:deluxe|standard|private|single|shared|general)\s+)*(?:room (?:charges|rent)|bed charges)(?:\s*[-–—]\s*.+)?", re.I)
_NURSING = re.compile(r"(?:dedicated\s+)?nursing(?: and monitoring| charges)?", re.I)


@dataclass(frozen=True)
class BillItem:
    number: int
    description: str
    quantity: int
    unit: str
    rate: Decimal
    amount: Decimal
    page: int


def find_bill_items(pages: list[str]) -> list[BillItem] | None:
    """Read one complete table bounded by its headers and printed summary."""
    unit_items = _read_unit_tables(pages)
    if unit_items is not None:
        return unit_items or None
    items = None
    for page_number, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        headers = [
            index for index in range(len(lines) - 3)
            if _HEADER.fullmatch(" ".join(lines[index:index + 4]).casefold())
        ]
        if not headers:
            continue
        if items is not None or len(headers) != 1:
            return None
        header = headers[0]
        numbered = header > 0 and _SERIAL_HEADER.fullmatch(lines[header - 1]) is not None
        start = header + 4
        end = next(
            (index for index in range(start, len(lines)) if total_field(lines[index]) == "gross"),
            None,
        )
        if end is None:
            return None
        body = lines[start:end]
        if body and body[-1].casefold().startswith("payment mode:"):
            body.pop()
        items = _read_rows(body, page_number, numbered=numbered)
        if not items:
            return None
    return items


def _read_unit_tables(pages):
    """Read tables with a separate unit column, including numbered continuations."""
    items = []
    found = False
    numbered_table = None
    for page, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        headers = [
            i for i in range(len(lines) - 4)
            if _UNIT_HEADER.fullmatch(" ".join(lines[i:i + 5]).casefold())
        ]
        if not headers:
            continue
        if len(headers) != 1:
            return []
        found = True
        header = headers[0]
        numbered = header > 0 and bool(_UNIT_SERIAL.fullmatch(lines[header - 1]))
        if numbered_table is not None and (not numbered or not numbered_table):
            return []
        numbered_table = numbered
        i = header + 5
        while i < len(lines) and not total_field(lines[i]) and not _TABLE_FOOTER.match(lines[i]):
            row = len(items) + 1
            if numbered:
                if lines[i] != str(row):
                    return []
                i += 1
            start = i
            while i < len(lines) and not lines[i].isdigit():
                if total_field(lines[i]) or parse_inr_amount(lines[i]) is not None:
                    return []
                i += 1
            if i == start or i + 3 >= len(lines) or int(lines[i]) < 1:
                return []
            unit, rate_text, amount_text = lines[i + 1:i + 4]
            rate, amount = map(parse_inr_amount, (rate_text, amount_text))
            if not re.fullmatch(r"[a-z][a-z -]*", unit, re.I) or rate is None or amount is None:
                return []
            items.append(BillItem(row, " ".join(lines[start:i]), int(lines[i]), unit, rate, amount, page))
            i += 4
    return items if found else None


def _read_rows(lines: list[str], page: int, *, numbered: bool) -> list[BillItem] | None:
    items = []
    index = 0
    while index < len(lines):
        row_number = len(items) + 1
        if numbered:
            if lines[index] != str(row_number):
                return None
            index += 1
        description = []
        while index < len(lines) and not _QUANTITY.fullmatch(lines[index]):
            if parse_inr_amount(lines[index]) is not None:
                return None
            description.append(lines[index])
            index += 1
        if not description or index + 2 >= len(lines):
            return None
        quantity = _QUANTITY.fullmatch(lines[index])
        rate = parse_inr_amount(lines[index + 1])
        amount = parse_inr_amount(lines[index + 2])
        if rate is None or amount is None:
            return None
        items.append(BillItem(
            number=row_number,
            description=" ".join(description),
            quantity=int(quantity["count"]),
            unit=quantity["unit"] or "",
            rate=rate,
            amount=amount,
            page=page,
        ))
        index += 3
    return items


def daily_room_and_nursing(items: list[BillItem]) -> tuple[BillItem, BillItem] | None:
    rooms = [item for item in items if _ROOM.fullmatch(item.description)]
    nursing = [item for item in items if _NURSING.fullmatch(item.description)]
    if len(rooms) != 1 or len(nursing) != 1:
        return None
    room, nurse = rooms[0], nursing[0]
    if room.quantity != nurse.quantity or any(
        item.unit.casefold() not in {"day", "days"} or item.quantity * item.rate != item.amount
        for item in (room, nurse)
    ):
        return None
    return room, nurse
