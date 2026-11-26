"""Find supporting item-level wording in a policy's expense annexure."""

import re
from collections import Counter
from dataclasses import dataclass


_ANNEXURE = re.compile(r"annexure\s*[-–—]?\s*([A-Z])", re.I)
_LIST = re.compile(r"(List\s+[IVXLCDM]+)\s*[-–—:]\s*(.+)", re.I)
_SHARED_HEADER = re.compile(r"(?:page\s+\d+(?:\s+of\s+\d+)?|uin\s*:.*|s\.?|no\.?|item)", re.I)
_WORD = re.compile(r"[^\W_]+")


@dataclass(frozen=True)
class ExpenseEntry:
    annexure: str
    list_name: str
    list_title: str
    number: int
    description: str
    first_page: int
    last_page: int

    @property
    def citation(self) -> str:
        pages = str(self.first_page)
        if self.last_page != self.first_page:
            pages += f"–{self.last_page}"
        return f"Annexure {self.annexure} · {self.list_name} · item {self.number} · PDF page {pages}"


def read_expense_entries(pages: list[str]) -> list[ExpenseEntry]:
    """Read numbered rows from exclusions and bundled-charge lists."""
    lines_by_page = [
        [" ".join(raw.split()) for raw in text.splitlines() if raw.strip()]
        for text in pages
    ]
    repeated = Counter(
        line.casefold() for lines in lines_by_page for line in set(lines[:4])
    )
    entries = []
    annexure = None
    list_info = None
    number = None
    description = []

    def finish_item():
        if not description:
            return
        entries.append(ExpenseEntry(
            annexure, *list_info, number,
            " ".join(text for _, text in description),
            first_page, description[-1][0],
        ))
        description.clear()

    for page, lines in enumerate(lines_by_page, 1):
        for line in lines:
            section = _ANNEXURE.fullmatch(line)
            if section:
                finish_item()
                annexure = section[1].upper()
                list_info = number = None
                continue
            if not annexure or _SHARED_HEADER.fullmatch(line) or repeated[line.casefold()] >= 3:
                continue
            heading = _LIST.fullmatch(line)
            if heading:
                finish_item()
                title = heading[2].casefold()
                list_info = (heading[1], heading[2]) if (
                    "coverage is not available" in title or "subsumed into" in title
                ) else None
                number = None
                continue
            if list_info is None:
                continue
            if line.isdecimal():
                expected = 1 if number is None else number + 1
                finish_item()
                if int(line) != expected:
                    list_info = number = None
                    continue
                number = expected
                first_page = page
            elif number is not None:
                description.append((page, line))
    finish_item()
    return entries


def match_expense_entries(
    item_name: str, entries: list[ExpenseEntry],
) -> tuple[list[ExpenseEntry], list[ExpenseEntry]]:
    """Find literal label matches and nearby phrases without inferring eligibility."""
    query = " ".join(_WORD.findall(item_name.casefold()))
    if not query:
        return [], []
    exact, related = [], []
    for entry in entries:
        label = " ".join(_WORD.findall(entry.description.casefold()))
        if label == query:
            exact.append(entry)
        elif f" {query} " in f" {label} " or f" {label} " in f" {query} ":
            related.append(entry)
    return exact, related
