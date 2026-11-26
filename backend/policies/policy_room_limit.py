"""Read the hospitalization room limit from supported policy wording."""

import re
from dataclasses import dataclass
from decimal import Decimal


_HOSPITALIZATION = re.compile(
    r"(?<!\d)4\.1\.?\s+hospitali[sz]ation\b(.*?)(?=\b4\.1\.1\b|$)",
    re.IGNORECASE,
)
_ROOM_CLAUSE = re.compile(
    r"\ba\.\s*(?P<excerpt>room rent\b.*?)(?=\s+b\.\s*intensive care|$)",
    re.IGNORECASE,
)
_LIMIT = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s+of\s+the\s+sum insured\s+"
    r"subject to\s+(?:a\s+)?maximum of\s+(?:rs\.?|inr|₹)\s*"
    r"([\d,]+(?:\.\d+)?)(?:\s*/\s*-)?\s*,?\s+per day\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RoomLimit:
    page: int
    excerpt: str
    percent: Decimal
    daily_cap: Decimal

    def daily_limit(self, sum_insured: Decimal) -> Decimal:
        return min(sum_insured * self.percent / 100, self.daily_cap)


def find_room_limit(pages: list[str]) -> RoomLimit | None:
    """Return the rule only when a single numbered policy clause supports it."""
    matches = []
    for page_number, text in enumerate(pages, start=1):
        normalized_text = " ".join(text.split())
        for section in _HOSPITALIZATION.finditer(normalized_text):
            clause = _ROOM_CLAUSE.search(section.group(1))
            if clause is None:
                continue
            limit = _LIMIT.search(clause.group("excerpt"))
            if limit:
                matches.append(
                    RoomLimit(
                        page=page_number,
                        excerpt=clause.group("excerpt")[:limit.end()].strip(),
                        percent=Decimal(limit.group(1)),
                        daily_cap=Decimal(limit.group(2).replace(",", "")),
                    )
                )

    return matches[0] if len(matches) == 1 else None
