"""Extract numbered waiting-period entries and calculate their completion dates."""

import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import date


_SECTION = re.compile(r"^6\.2\.?\s+specific waiting period\s*:?(?:\s*\(.*\))?$", re.I)
_NEXT_SECTION = re.compile(r"^6\.([3-9]|\d{2,})\.?\s+\D")
_GROUP = re.compile(r"^\(([ivxlcdm]+)\)\s+([1-9]\d{0,2})\s+months? waiting period\s*:?$", re.I)
_ITEM = re.compile(r"^([1-9]\d*)\.\s+(.+)$")
_PAGE_HEADER = re.compile(r"^(?:page \d+ of \d+|uin\s*:.*|arogya sanjeevani policy,.*)$", re.I)
_WORDS = re.compile(r"[^\W\d_]+")
_COMMON_WORDS = {"arising", "excluding", "related", "treatment", "unless"}
_CODED_SECTION = re.compile(
    r"^\d+\.\s+specifi\s*ed disease\s*/\s*procedure waiting period",
    re.I | re.M,
)
_CODED_ITEM = re.compile(r"^([ivxlcdm]+)\.\s*", re.I | re.M)


@dataclass(frozen=True)
class WaitingPeriodRule:
    group: str
    item: int
    months: int
    condition: str
    first_page: int
    last_page: int
    clause_reference: str | None = None

    @property
    def clause(self) -> str:
        return self.clause_reference or f"6.2({self.group}), item {self.item}"

    def completion_date(self, start: date) -> date:
        return add_coverage_months(start, self.months)


def add_coverage_months(start: date, months: int) -> date:
    year, month_offset = divmod(start.year * 12 + start.month - 1 + months, 12)
    month = month_offset + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def find_waiting_period_rules(pages: list[str]) -> list[WaitingPeriodRule]:
    """Read numbered items under each duration in the supported policy section."""
    entries: dict[tuple[str, int, int], list[tuple[int, str]]] = {}
    in_section = False
    group = None
    active_item = None
    for page_number, text in enumerate(pages, start=1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line or _PAGE_HEADER.fullmatch(line):
                continue
            if _SECTION.fullmatch(line):
                in_section = True
                group = active_item = None
                continue
            if not in_section:
                continue
            if _NEXT_SECTION.match(line):
                in_section = False
                continue
            duration = _GROUP.fullmatch(line)
            if duration:
                group = (duration[1].lower(), int(duration[2]))
                active_item = None
                continue
            if group is None:
                continue
            item = _ITEM.fullmatch(line)
            if item:
                key = (*group, int(item[1]))
                if key in entries:
                    return []
                active_item = entries[key] = [(page_number, item[2])]
            elif active_item is not None:
                active_item.append((page_number, line))
    rules = [
        WaitingPeriodRule(group, item, months, " ".join(text for _, text in source),
                          source[0][0], source[-1][0])
        for (group, months, item), source in entries.items()
    ]
    return rules or _coded_waiting_rules(pages)


def _coded_waiting_rules(pages: list[str]) -> list[WaitingPeriodRule]:
    """Keep a coded exclusion's stated duration attached to its own list."""
    rules = []
    for page_number, page in enumerate(pages, start=1):
        text = unicodedata.normalize("NFKC", page)
        heading = _CODED_SECTION.search(text)
        if not heading:
            continue
        section = re.split(r"^\d+\.\s+[^\n]*waiting period", text[heading.end():],
                           maxsplit=1, flags=re.I | re.M)[0]
        code = re.search(r"\bCode\s+(Excl\s*\d+)\b", section, re.I)
        intro, *lists = re.split(r"^\s*[A-Z]\.\s+List of specifi\s*c diseases\s*/\s*procedures\b",
                                 section, maxsplit=1, flags=re.I | re.M)
        durations = set(re.findall(r"\b(\d+)\s+months? of continuous coverage\b", intro, re.I))
        if not (code and lists and len(durations) == 1):
            continue
        items = _CODED_ITEM.split(lists[0])
        for index, (label, condition) in enumerate(zip(items[1::2], items[2::2]), start=1):
            reference = f"{' '.join(code[1].split())}, item {label.lower()}"
            rules.append(WaitingPeriodRule(label, index, int(next(iter(durations))),
                                           " ".join(condition.split()), page_number,
                                           page_number, reference))
    return rules


def suggest_waiting_period_rules(
    rules: list[WaitingPeriodRule], reviewed_values: list[str]
) -> list[WaitingPeriodRule]:
    """Suggest entries with overlapping clinical words for user confirmation."""
    def words(text):
        return {
            word for word in _WORDS.findall(text.casefold())
            if len(word) >= 4 and word not in _COMMON_WORDS
        }

    reviewed_words = words(" ".join(reviewed_values))
    return [rule for rule in rules if reviewed_words & words(rule.condition)]
