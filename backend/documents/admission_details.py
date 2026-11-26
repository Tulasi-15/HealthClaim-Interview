"""Read and compare patient and admission labels in digital hospital PDFs."""

import re
from dataclasses import dataclass
from datetime import datetime


ADMISSION_FIELDS = ("Patient name", "Patient ID", "Admission date", "Discharge date")
_LABEL_ALIASES = {
    "patient": "patient name", "beneficiary name": "patient name",
    "uhid / patient id": "patient id", "mrn": "patient id",
    "admitted": "admission date", "admitted on": "admission date",
    "date of admission": "admission date", "date of entry": "admission date",
    "discharged": "discharge date", "discharged on": "discharge date",
    "date of discharge": "discharge date", "date of exit": "discharge date",
}
_FIELD_LINE = re.compile(
    r"(" + "|".join(re.escape(label) for label in (*ADMISSION_FIELDS, *_LABEL_ALIASES)) + r"):\s*(.*)",
    re.I,
)
_SUMMARY_TITLE = re.compile(r"^(?:inpatient\s+)?(?:discharge\s+summary|clinical discharge note)\b", re.I | re.M)
_PATIENT_ID = re.compile(r"[A-Z0-9]+(?:[-/][A-Z0-9]+)*", re.I)
_INLINE_ID = re.compile(r"(.+?)\s*\((?:patient\s+)?id:\s*([^()]+)\)", re.I)
_FIELD_SEPARATOR = re.compile(r"\s*\|\s*|\s{2,}(?=[A-Za-z][A-Za-z /]{1,30}:)")


@dataclass(frozen=True)
class AdmissionValue:
    text: str
    normalized: str
    page: int


def read_hospital_name(pages: list[str]) -> AdmissionValue | None:
    """Find a plausible provider name in a header immediately above an address."""
    for page_number, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()][:14]
        for index, line in enumerate(lines):
            if not re.match(r"^\d+\s+\S", line):
                continue
            header = []
            for candidate in reversed(lines[max(0, index - 2):index]):
                if not candidate.isupper() or not re.fullmatch(r"[\w &.'-]+", candidate):
                    break
                header.insert(0, candidate)
            name = " ".join(header)
            if header and re.search(
                r"\b(?:hospital|medical cent(?:re|er)|institute of health|clinic|surgical guild)\b",
                header[-1] if len(header) == 1 else name, re.I,
            ) and not re.search(r"\b(?:synthetic test document|final bill|discharge summary)\b", name, re.I):
                return AdmissionValue(name, name.casefold(), page_number)
    return None


def has_discharge_summary_title(pages: list[str]) -> bool:
    return any(_SUMMARY_TITLE.search(text) for text in pages)


def read_admission_details(pages: list[str]) -> dict[str, AdmissionValue]:
    """Return fields with a single normalized value across the document."""
    values: dict[str, dict[str, AdmissionValue]] = {
        field.casefold(): {} for field in ADMISSION_FIELDS
    }
    for page_number, text in enumerate(pages, start=1):
        lines = [
            part.strip() for line in text.splitlines()
            for part in _FIELD_SEPARATOR.split(line) if part.strip()
        ]
        for index, line in enumerate(lines):
            match = _FIELD_LINE.fullmatch(line)
            if match is None:
                continue
            field, raw = match[1].casefold(), match[2]
            field = _LABEL_ALIASES.get(field, field)
            if not raw and index + 1 < len(lines):
                raw = lines[index + 1]
            raw = " ".join(raw.split())
            if field == "patient name" and (inline := _INLINE_ID.fullmatch(raw)):
                raw, patient_id = inline.groups()
                normalized_id = _normalize("patient id", patient_id)
                if normalized_id:
                    values["patient id"].setdefault(
                        normalized_id, AdmissionValue(patient_id, normalized_id, page_number)
                    )
            normalized = _normalize(field, raw)
            if normalized is not None:
                values[field].setdefault(normalized, AdmissionValue(raw, normalized, page_number))
    return {
        field: next(iter(values[field.casefold()].values()))
        for field in ADMISSION_FIELDS
        if len(values[field.casefold()]) == 1
    }


def _normalize(field: str, raw: str) -> str | None:
    if field.endswith("date"):
        for date_format in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, date_format).date().isoformat()
            except ValueError:
                continue
        return None
    if field == "patient id":
        return raw.upper() if _PATIENT_ID.fullmatch(raw) else None
    if raw and any(char.isalpha() for char in raw) and all(
        char.isalpha() or char in " .'-’" for char in raw
    ):
        return raw.casefold()
    return None
