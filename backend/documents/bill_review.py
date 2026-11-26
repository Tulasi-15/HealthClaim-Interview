"""Review bill rows and retain the original extraction in local storage."""

import json
import sqlite3
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256

import streamlit as st

from backend.documents.bill_items import BillItem
from backend.storage.local_database import open_local_database


def _encode(items):
    return json.dumps([asdict(item) for item in items], default=str, sort_keys=True)


def _decode(payload):
    rows = json.loads(payload)
    return [BillItem(**{**row, "rate": Decimal(row["rate"]), "amount": Decimal(row["amount"])}) for row in rows]


def _history(document_hash):
    with open_local_database() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bill_row_reviews (
                id INTEGER PRIMARY KEY,
                document_hash TEXT NOT NULL,
                original TEXT NOT NULL,
                reviewed TEXT NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        return [dict(row) for row in connection.execute(
            "SELECT * FROM bill_row_reviews WHERE document_hash = ? ORDER BY id DESC",
            (document_hash,),
        )]


def save_bill_rows(document_hash, originals, reviewed):
    _history(document_hash)
    original, updated = _encode(originals), _encode(reviewed)
    with open_local_database() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute(
            "SELECT reviewed FROM bill_row_reviews WHERE document_hash = ? ORDER BY id DESC LIMIT 1",
            (document_hash,),
        ).fetchone()
        if latest is None or latest["reviewed"] != updated:
            connection.execute(
                "INSERT INTO bill_row_reviews (document_hash, original, reviewed) VALUES (?, ?, ?)",
                (document_hash, original, updated),
            )


def parse_reviewed_rows(originals, rows):
    reviewed = []
    for original, row in zip(originals, rows, strict=True):
        try:
            quantity = Decimal(str(row["Quantity"]))
            rate = Decimal(str(row["Rate (₹)"]))
            amount = Decimal(str(row["Amount (₹)"]))
            if (
                not all(value.is_finite() for value in (quantity, rate, amount))
                or quantity <= 0 or quantity != quantity.to_integral_value()
                or min(rate, amount) < 0
                or any(value != value.quantize(Decimal("0.01")) for value in (rate, amount))
            ):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"Check the quantity, rate, and amount on row {original.number}.") from None
        reviewed.append(BillItem(
            original.number, original.description, int(quantity), original.unit,
            rate, amount, original.page,
        ))
    return reviewed


def show_bill_row_review(items, document_hash):
    try:
        history = _history(document_hash)
    except (OSError, sqlite3.Error):
        st.error("Could not open bill review storage.")
        return items, document_hash, False
    active = _decode(history[0]["reviewed"]) if history else items
    with st.expander("Review and correct expense rows"):
        st.caption("Check each value against the original PDF below. Saved rows are used for arithmetic checks.")
        with st.form(f"bill_review_{document_hash}"):
            edits = st.data_editor(
                [{
                    "Row": item.number, "Expense": item.description, "PDF page": item.page,
                    "Quantity": item.quantity, "Unit": item.unit,
                    "Rate (₹)": str(item.rate), "Amount (₹)": str(item.amount),
                } for item in active],
                disabled=["Row", "Expense", "PDF page", "Unit"],
                hide_index=True,
                key=f"bill_rows_{document_hash}",
            )
            confirmed = st.checkbox("I checked these expense values against the original bill.")
            if st.form_submit_button("Save bill row review"):
                if not confirmed:
                    st.warning("Confirm the bill review before saving.")
                else:
                    try:
                        updated = parse_reviewed_rows(items, edits)
                        save_bill_rows(document_hash, items, updated)
                        active = updated
                        history = _history(document_hash)
                        st.success("Bill row review saved.")
                    except ValueError as error:
                        st.warning(str(error))
                    except (OSError, sqlite3.Error):
                        st.error("Could not save the bill review.")
        if history:
            st.caption(f"Using bill review #{history[0]['id']} · {history[0]['saved_at']} UTC")
            with st.expander("Bill review history"):
                for revision in history:
                    st.write(f"Review #{revision['id']} · {revision['saved_at']} UTC")
                    st.json({
                        "Original extraction": json.loads(revision["original"]),
                        "Reviewed rows": json.loads(revision["reviewed"]),
                    })
    fingerprint = sha256((document_hash + _encode(active)).encode()).hexdigest()
    return active, fingerprint, bool(history)
