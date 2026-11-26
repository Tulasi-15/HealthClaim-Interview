"""Save reviewed bill totals with their original extraction and source pages."""

import json
import sqlite3
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256

import streamlit as st

from backend.documents.bill_totals import BillTotal, BillTotals
from backend.storage.local_database import open_local_database


TOTAL_FIELDS = {
    "gross": "Gross charges",
    "discount": "Discount",
    "net": "Net charges",
    "advance": "Advance payment",
    "balance": "Balance due",
}


def _encode(totals):
    return json.dumps(asdict(totals), default=str, sort_keys=True)


def _decode(payload):
    return BillTotals(**{
        field: BillTotal(Decimal(value["amount"]), value["page"]) if value else None
        for field, value in json.loads(payload).items()
    })


def load_total_reviews(document_hash):
    with open_local_database() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bill_total_reviews (
                id INTEGER PRIMARY KEY,
                document_hash TEXT NOT NULL,
                original TEXT NOT NULL,
                reviewed TEXT NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        return [dict(row) for row in connection.execute(
            "SELECT * FROM bill_total_reviews WHERE document_hash = ? ORDER BY id DESC",
            (document_hash,),
        )]


def save_total_review(document_hash, originals, reviewed):
    load_total_reviews(document_hash)
    original, updated = _encode(originals), _encode(reviewed)
    with open_local_database() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute(
            "SELECT reviewed FROM bill_total_reviews WHERE document_hash = ? ORDER BY id DESC LIMIT 1",
            (document_hash,),
        ).fetchone()
        if latest is None or latest["reviewed"] != updated:
            connection.execute(
                "INSERT INTO bill_total_reviews (document_hash, original, reviewed) VALUES (?, ?, ?)",
                (document_hash, original, updated),
            )


def parse_total_review(rows, page_count):
    if len(rows) != len(TOTAL_FIELDS):
        raise ValueError("Review all five bill total fields.")
    values = {}
    for field, row in zip(TOTAL_FIELDS, rows, strict=True):
        raw_amount = row["Amount (₹)"]
        text = "" if raw_amount is None else str(raw_amount).strip()
        if not text:
            values[field] = None
            continue
        try:
            amount = Decimal(text)
            page = Decimal(str(row["PDF page"]))
            if (
                not amount.is_finite() or amount < 0
                or amount != amount.quantize(Decimal("0.01"))
                or not page.is_finite() or page != page.to_integral_value()
                or not 1 <= page <= page_count
            ):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"Check the amount and source page for {TOTAL_FIELDS[field].lower()}.") from None
        values[field] = BillTotal(amount, int(page))
    return BillTotals(**values)


def show_bill_total_review(totals, document_hash, page_count):
    originals = totals or BillTotals()
    try:
        history = load_total_reviews(document_hash)
    except (OSError, sqlite3.Error):
        st.error("Could not open bill total review storage.")
        return totals, ""
    active = _decode(history[0]["reviewed"]) if history else originals
    with st.expander("Review and correct bill totals"):
        st.caption(
            "Use amounts from the original PDF. Leave unavailable amounts blank. "
            "Enter discounts and advances as positive amounts, with their source page."
        )
        with st.form(f"bill_total_review_{document_hash}"):
            rows = []
            for field, label in TOTAL_FIELDS.items():
                value = getattr(active, field)
                rows.append({
                    "Field": label,
                    "Amount (₹)": str(value.amount) if value else "",
                    "PDF page": str(value.page) if value else "",
                })
            edits = st.data_editor(
                rows, disabled=["Field"], hide_index=True,
                key=f"bill_total_values_{document_hash}",
            )
            confirmed = st.checkbox("I checked these totals and source pages against the original bill.")
            if st.form_submit_button("Save bill totals review"):
                if not confirmed:
                    st.warning("Confirm the totals review before saving.")
                else:
                    try:
                        updated = parse_total_review(edits, page_count)
                        save_total_review(document_hash, originals, updated)
                        active = updated
                        history = load_total_reviews(document_hash)
                        st.success("Bill totals review saved.")
                    except ValueError as error:
                        st.warning(str(error))
                    except (OSError, sqlite3.Error):
                        st.error("Could not save the bill totals review.")
        if history:
            st.caption(f"Using totals review #{history[0]['id']} · {history[0]['saved_at']} UTC")
            with st.expander("Bill totals review history"):
                for revision in history:
                    st.write(f"Review #{revision['id']} · {revision['saved_at']} UTC")
                    st.json({
                        "Original extraction": json.loads(revision["original"]),
                        "Reviewed totals": json.loads(revision["reviewed"]),
                    })
    # Preserve existing estimate identities until a totals review is actually saved.
    fingerprint = sha256(_encode(active).encode()).hexdigest() if history else ""
    return active if history else totals, fingerprint
