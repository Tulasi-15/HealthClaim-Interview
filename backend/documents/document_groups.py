"""Identify hospital document pages and preserve their original page numbers."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentGroup:
    kind: str
    start_page: int
    end_page: int


def classify_heading(text):
    header = " ".join(text.split()[:105]).casefold()
    if re.search(r"\b(?:lab(?:oratory)? report|pathology report)\b", header):
        return "Lab Report"
    if re.search(r"\b(?:discharge summary|clinical discharge note|discharge note)\b", header):
        return "Discharge Summary"
    if re.search(r"\b(?:pharmacy invoice|pharmacy bill)\b", header) or (
        re.search(r"\b(?:tax invoice|invoice (?:number|no))\b", header)
        and re.search(r"\b(?:pharmacy|dispensary)\b", header)
    ):
        return "Pharmacy Bill"
    if re.search(r"\bitemi[sz]ed hospital (?:bill|statement)\b", header):
        return "Itemized Hospital Bill"
    if re.search(r"\b(?:final bill|final hospital bill|hospital final bill|inpatient bill|patient account statement|inpatient statement of account)\b", header):
        return "Final Hospital Bill"
    return None


def group_document_pages(pages, classify):
    groups = []
    hospital_bill_types = {"Final Hospital Bill", "Itemized Hospital Bill"}
    for number, text in enumerate(pages, 1):
        kind = classify(text)
        header = " ".join(text.split()[:75]).casefold()
        continuation = re.search(r"\bcontinu(?:ed|ation)\b|\bbill page [2-9]\d* of\b", header)
        if groups and continuation and (
            kind == groups[-1].kind or {kind, groups[-1].kind} <= hospital_bill_types
        ):
            previous = groups[-1]
            groups[-1] = DocumentGroup(previous.kind, previous.start_page, number)
        else:
            groups.append(DocumentGroup(kind, number, number))
    return groups
