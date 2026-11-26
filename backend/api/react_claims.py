"""Document and estimate operations shared with the React API."""

from dataclasses import dataclass
from hashlib import sha256

import pymupdf
import pytesseract
from PIL import Image

from backend.documents.admission_details import read_admission_details, read_hospital_name
from backend.documents.bill_items import find_bill_items
from backend.documents.bill_review import _decode as decode_items, _encode as encode_items, _history as row_history
from backend.documents.bill_total_review import _decode as decode_totals, _encode as encode_totals, load_total_reviews
from backend.documents.bill_totals import find_bill_totals
from backend.documents.clinical_details import read_clinical_details
from backend.storage.clinical_review_store import current_values, load_clinical_history
from backend.documents.document_groups import classify_heading, group_document_pages
from backend.documents.scanned_bill import normalize_scanned_bill


def fingerprint(value):
    return sha256(value).hexdigest()


def policy_pages(file):
    if not file:
        return []
    with pymupdf.open(stream=file.content, filetype="pdf") as pdf:
        return [page.get_text() for page in pdf]


def _recognize(page, dpi, mode):
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    return pytesseract.image_to_string(image, lang="eng", config=f"--psm {mode} -c preserve_interword_spaces=1")


def document_pages(file):
    raw, structured, scanned = [], [], set()
    with pymupdf.open(stream=file.content, filetype="pdf") as pdf:
        for number, page in enumerate(pdf, 1):
            text = page.get_text()
            candidate = text
            if not text.strip():
                scanned.add(number)
                try:
                    text = _recognize(page, 250, 3)
                    candidate = normalize_scanned_bill(text)
                    items = find_bill_items([candidate])
                    totals = find_bill_totals([candidate])
                    conflict = totals and any(not ok for ok, _ in totals.reconciliation_checks())
                    if not items or conflict:
                        retry = _recognize(page, 350 if not items else 400, 4 if not items else 3)
                        retry_candidate = normalize_scanned_bill(retry)
                        retry_totals = find_bill_totals([retry_candidate])
                        checks = retry_totals.reconciliation_checks() if retry_totals else []
                        if len(checks) == 2 and all(ok for ok, _ in checks) and (
                            find_bill_items([retry_candidate]) or (not items and conflict)
                        ):
                            text, candidate = retry, retry_candidate
                except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError):
                    pass
            raw.append(text)
            structured.append(candidate)
    groups = group_document_pages(raw, lambda text: classify_heading(text) or "Unknown Document")
    return raw, structured, scanned, groups


@dataclass
class BillReview:
    key: str
    original_items: list
    original_totals: object
    items: list
    totals: object
    page_count: int
    scanned: bool
    rows_confirmed: bool
    identity: str
    groups: list
    fields: dict
    findings: dict
    reviewed_clinical: dict


def read_bill(file, start_page=None, *, summary_page=None):
    raw, pages, scans, groups = document_pages(file)
    bills = [group for group in groups if group.kind.endswith("Hospital Bill")]
    group = next((item for item in bills if item.start_page == start_page), None) if start_page else (
        bills[0] if bills else None
    )
    if start_page and group is None:
        raise ValueError("Select a recognized hospital bill group.")
    key = fingerprint(file.content)
    if group and len(groups) > 1:
        key = fingerprint(f"{key}:{group.start_page}:{group.end_page}".encode())
        pages = [text if group.start_page <= number <= group.end_page else ""
                 for number, text in enumerate(pages, 1)]
        scans = {number for number in scans if group.start_page <= number <= group.end_page}
    originals = find_bill_items(pages) or []
    original_totals = find_bill_totals(pages)
    rows, totals_history = row_history(key), load_total_reviews(key)
    items = decode_items(rows[0]["reviewed"]) if rows else originals
    totals = decode_totals(totals_history[0]["reviewed"]) if totals_history else original_totals
    identity = fingerprint((key + encode_items(items)).encode()) if items else key
    if totals_history:
        identity = fingerprint((identity + fingerprint(encode_totals(totals).encode())).encode())
    fields = {}
    for part in groups:
        source = [text if part.start_page <= number <= part.end_page else ""
                  for number, text in enumerate(raw, 1)]
        part_fields = {**read_admission_details(source), **read_clinical_details(source)}
        if hospital := read_hospital_name(source):
            part_fields["Hospital name"] = hospital
        fields[part.start_page] = part_fields
    clinical_groups = [item for item in groups if item.kind == "Discharge Summary"]
    clinical_group = next((item for item in clinical_groups if item.start_page == summary_page), None) if summary_page else (
        clinical_groups[0] if clinical_groups and not group else group
    )
    if summary_page and clinical_group is None:
        raise ValueError("Select a recognized discharge summary.")
    clinical_source = [text if clinical_group is None or clinical_group.start_page <= number <= clinical_group.end_page
                       else "" for number, text in enumerate(raw, 1)]
    findings = read_clinical_details(clinical_source)
    reviewed = current_values(load_clinical_history(clinical_key(file, summary_page, clinical_groups)))
    if summary_page is not None:
        fields = {summary_page: fields.get(summary_page, {})}
    return BillReview(key, originals, original_totals, items, totals, len(pages), bool(scans),
                      bool(rows), identity, groups, fields, findings, reviewed)


def clinical_key(file, summary_page, groups):
    key = fingerprint(file.content)
    if summary_page and len(groups) > 1 and summary_page != groups[0].start_page:
        return fingerprint(f"{key}:summary:{summary_page}".encode())
    return key


def estimate_ready(bill):
    totals = bill.totals
    return bool(
        bill.items and totals and totals.net and totals.gross and totals.discount
        and (not bill.scanned or bill.rows_confirmed)
        and all(ok for ok, _ in totals.reconciliation_checks())
        and sum(item.amount for item in bill.items) == totals.gross.amount
        and all(item.quantity * item.rate == item.amount for item in bill.items)
    )
