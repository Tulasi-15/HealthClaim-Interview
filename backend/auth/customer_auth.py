"""Email and password authentication for customer accounts."""

import hashlib
import hmac
import re
import secrets

import psycopg
import streamlit as st

from backend.storage.postgres_storage import connect


def _password_digest(password, salt):
    return hashlib.scrypt(
        password.encode(), salt=salt, n=2**16, r=8, p=2,
        maxmem=128 * 1024 * 1024,
    )


def _register(email, password):
    salt = secrets.token_bytes(16)
    digest = _password_digest(password, salt)
    with connect() as connection:
        row = connection.execute(
            """INSERT INTO customers (issuer, subject, display_email, password_verifier)
               VALUES ('local', %s, %s, %s)
               ON CONFLICT (issuer, subject) DO NOTHING RETURNING id""",
            (email, email, salt + digest),
        ).fetchone()
        return row is not None


def _authenticate(email, password):
    with connect() as connection:
        row = connection.execute(
            """SELECT id, password_verifier FROM customers
               WHERE issuer = 'local' AND subject = %s""", (email,),
        ).fetchone()
    verifier = (row and row["password_verifier"]) or bytes(80)
    matches = hmac.compare_digest(_password_digest(password, verifier[:16]), verifier[16:])
    return str(row["id"]) if matches and row and row["password_verifier"] else None


def google_customer(subject, email):
    with connect() as connection:
        row = connection.execute(
            """INSERT INTO customers (issuer, subject, display_email)
               VALUES ('google', %s, %s)
               ON CONFLICT (issuer, subject) DO NOTHING RETURNING id""",
            (subject, email),
        ).fetchone()
        if not row:
            row = connection.execute(
                "SELECT id FROM customers WHERE issuer = 'google' AND subject = %s",
                (subject,),
            ).fetchone()
        return str(row["id"])


def require_customer():
    if st.session_state.get("customer_id"):
        if st.sidebar.button("Sign out"):
            st.session_state.clear()
            st.rerun()
        return

    st.subheader("Your policy workspace")
    action = st.radio("Account", ["Sign in", "Create account"], horizontal=True)
    registering = action == "Create account"
    with st.form(f"customer_{action}", clear_on_submit=True):
        email = st.text_input("Email", max_chars=254).strip().lower()
        password = st.text_input("Password", type="password", max_chars=256)
        confirmation = (
            st.text_input("Confirm password", type="password", max_chars=256)
            if registering else None
        )
        submitted = st.form_submit_button(action, type="primary")

    if submitted:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not password:
            st.error("Enter a valid email address and password.")
        elif registering and (len(password) < 12 or password != confirmation):
            st.error("Use at least 12 characters and confirm the same password.")
        else:
            try:
                if registering:
                    if _register(email, password):
                        st.success("Account created. Select Sign in to continue.")
                    else:
                        st.warning("An account already exists for this email. Please sign in.")
                else:
                    customer_id = _authenticate(email, password)
                    if customer_id:
                        st.session_state.clear()
                        st.session_state["customer_id"] = customer_id
                        st.rerun()
                    st.error("Email or password is incorrect.")
            except (OSError, psycopg.Error):
                st.error("Could not access customer accounts. Check the PostgreSQL setup.")
    st.stop()
