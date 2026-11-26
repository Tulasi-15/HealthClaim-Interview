"""PostgreSQL connections bound to the authenticated Streamlit session."""

import os
import tomllib
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import psycopg
import streamlit as st
from psycopg.rows import dict_row
from streamlit.errors import StreamlitSecretNotFoundError


def database_url():
    """Allow deployment overrides and load saved settings for local launches."""
    url = os.environ.get("CLAIMS_DATABASE_URL")
    if url:
        return url
    local_secrets = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml"
    if local_secrets.is_file():
        with local_secrets.open("rb") as handle:
            return tomllib.load(handle).get("database", {}).get("url")
    try:
        return st.secrets.get("database", {}).get("url")
    except StreamlitSecretNotFoundError:
        return None


@contextmanager
def connect():
    url = database_url()
    if not url:
        raise OSError("Set CLAIMS_DATABASE_URL to the PostgreSQL connection string.")
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as connection:
        role = connection.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        if role["rolsuper"] or role["rolbypassrls"]:
            raise OSError("Use a restricted application role for CLAIMS_DATABASE_URL.")
        yield connection


class StoreConnection:
    """Bridge existing store statements to PostgreSQL parameter binding."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        normalized = statement.strip().upper()
        if normalized.startswith("CREATE "):
            return None  # Schema is applied by the database setup script.
        if normalized == "BEGIN IMMEDIATE":
            self.connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(current_setting('app.customer_id')))"
            )
            return None
        statement = statement.replace("?", "%s")
        if normalized.startswith(("INSERT INTO CLAIMS (", "INSERT INTO CLAIM_ESTIMATE_REVISIONS (")):
            row = self.connection.execute(statement + " RETURNING id", parameters).fetchone()
            return SimpleNamespace(lastrowid=row["id"])
        return self.connection.execute(statement, parameters)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def executemany(self, statement, parameters):
        with self.connection.cursor() as cursor:
            cursor.executemany(statement.replace("?", "%s"), parameters)

    def executescript(self, statement):
        # Legacy SQLite schema initialization is handled by the setup script.
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@contextmanager
def customer_connection(customer_id):
    try:
        with connect() as connection:
            connection.execute("SELECT set_config('app.customer_id', %s, true)", (customer_id,))
            yield StoreConnection(connection)
    except psycopg.Error as error:
        raise OSError("Could not access PostgreSQL customer storage.") from error
