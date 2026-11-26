"""Store reviewed clinical values and their change history in local SQLite."""

from contextlib import contextmanager
from dataclasses import dataclass

from backend.documents.clinical_details import ClinicalFinding
from backend.storage.local_database import open_local_database


@dataclass(frozen=True)
class ClinicalRevision:
    field: str
    previous_value: str | None
    reviewed_value: str | None
    extracted_value: str | None
    source_page: int | None
    saved_at: str


@contextmanager
def _connection():
    with open_local_database() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS clinical_review_revisions (
                id INTEGER PRIMARY KEY,
                document_hash TEXT NOT NULL,
                field TEXT NOT NULL,
                previous_value TEXT,
                reviewed_value TEXT,
                extracted_value TEXT,
                source_page INTEGER,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS clinical_revisions_by_document
            ON clinical_review_revisions (document_hash, id)
        """)
        yield connection


def current_values(history: list[ClinicalRevision]) -> dict[str, str | None]:
    """Read the latest value per field from newest-first history."""
    values: dict[str, str | None] = {}
    for revision in history:
        values.setdefault(revision.field, revision.reviewed_value)
    return values


def _read_history(connection, document_hash: str) -> list[ClinicalRevision]:
    rows = connection.execute("""
        SELECT field, previous_value, reviewed_value, extracted_value, source_page, saved_at
        FROM clinical_review_revisions
        WHERE document_hash = ?
        ORDER BY id DESC
    """, (document_hash,))
    return [ClinicalRevision(**dict(row)) for row in rows]


def load_clinical_history(document_hash: str) -> list[ClinicalRevision]:
    with _connection() as connection:
        return _read_history(connection, document_hash)


def save_clinical_review(
    document_hash: str,
    reviewed: dict[str, str],
    findings: dict[str, ClinicalFinding],
) -> list[ClinicalRevision]:
    """Append changed fields together and return the current history."""
    with _connection() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        history = _read_history(connection, document_hash)
        values = current_values(history)
        for field, text in reviewed.items():
            value = text or None
            if values.get(field) == value:
                continue
            finding = findings.get(field)
            connection.execute("""
                INSERT INTO clinical_review_revisions (
                    document_hash, field, previous_value, reviewed_value,
                    extracted_value, source_page
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                document_hash, field, values.get(field), value,
                finding.text if finding else None, finding.page if finding else None,
            ))
        return _read_history(connection, document_hash)
