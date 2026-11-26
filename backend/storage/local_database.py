"""Open the local application database."""

import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

request_customer = ContextVar("request_customer", default=None)


def local_data_directory():
    configured_path = os.environ.get("CLAIMS_DATA_DIR")
    user_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    directory = Path(configured_path).expanduser() if configured_path else user_data / "HealthcareClaimsAssist"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def open_local_database():
    from backend.storage.postgres_storage import customer_connection, database_url

    customer_id = request_customer.get()
    if not customer_id:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True):
            customer_id = st.session_state.get("customer_id")
    if customer_id:
        with customer_connection(customer_id) as connection:
            yield connection
        return
    if database_url():
        raise OSError("Sign in to access customer records.")
    directory = local_data_directory()
    connection = sqlite3.connect(directory / "claims.sqlite3")
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()
