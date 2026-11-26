"""Read the diagnosis and procedure sections of digital discharge summaries."""

import re
from dataclasses import dataclass


CLINICAL_FIELDS = ("Primary diagnosis", "Procedure performed")
_HEADING = re.compile(
    r"(primary diagnosis|clinical condition|diagnosis|procedure performed|procedure(?=\s*:)|intervention)"
    r"(?:\s*:\s*(.*))?", re.I,
)
_SECTION_BOUNDARY = re.compile(
    r"(?:secondary diagnosis|anaesthesia|anesthesia|(?:key )?investigations(?: done)?|"
    r"(?:clinical summary & )?hospital course|condition at discharge|"
    r"discharge advice(?: & medications)?|follow-up schedule|clinical presentation|"
    r"surgical procedure|clinical course|discharge condition & advice|"
    r"description|line|expense item|code\b.*charge head.*)(?:\s*:.*)?",
    re.I,
)


@dataclass(frozen=True)
class ClinicalFinding:
    text: str
    page: int


def _clinical_lines(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        columns = re.split(r"\s{2,}(?=intervention\s*:)", line, flags=re.I)
        if len(columns) != 2 or not columns[0].casefold().startswith("clinical condition:"):
            continue
        continuation = re.split(r"\s{2,}", lines[index + 1], maxsplit=1)
        if len(continuation) == 2 and all(re.fullmatch(r"[A-Za-z][A-Za-z -]+", part) for part in continuation):
            columns = [f"{column} {part}" for column, part in zip(columns, continuation)]
            return [*lines[:index], *columns, *lines[index + 2:]]
        return [*lines[:index], *columns, *lines[index + 1:]]
    return lines


def read_clinical_details(pages: list[str]) -> dict[str, ClinicalFinding]:
    """Return values bounded by recognizable sections on the same PDF page."""
    findings: dict[str, dict[str, ClinicalFinding]] = {
        field.casefold(): {} for field in CLINICAL_FIELDS
    }
    for page_number, text in enumerate(pages, start=1):
        lines = _clinical_lines(text)
        for index, line in enumerate(lines):
            heading = _HEADING.fullmatch(line)
            if heading is None:
                continue
            parts = [heading[2]] if heading[2] else []
            for following in lines[index + 1:]:
                if _HEADING.fullmatch(following) or _SECTION_BOUNDARY.fullmatch(following):
                    break
                parts.append(following)
            else:
                if len(parts) > 1:
                    continue
            value = " ".join(" ".join(parts).split())
            if value:
                field = (
                    "primary diagnosis"
                    if heading[1].casefold() in {"primary diagnosis", "clinical condition", "diagnosis"}
                    else "procedure performed"
                )
                findings[field].setdefault(value, ClinicalFinding(value, page_number))
    return {
        field: next(iter(findings[field.casefold()].values()))
        for field in CLINICAL_FIELDS
        if len(findings[field.casefold()]) == 1
    }
