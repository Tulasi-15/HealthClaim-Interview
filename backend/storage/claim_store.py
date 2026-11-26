"""Save and reopen a claim's original PDFs and policy inputs."""

import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pymupdf

from backend.storage.local_database import local_data_directory, open_local_database


_DOCUMENT_KEY = re.compile(r"[0-9a-f]{32}\.pdf")


@dataclass(frozen=True)
class ClaimPDF:
    name: str
    content: bytes
    storage_key: str | None = field(default=None, repr=False, compare=False)

    def getvalue(self) -> bytes:
        return self.content


@dataclass(frozen=True)
class SavedClaim:
    name: str
    sum_insured: int | None
    policy: ClaimPDF | None
    hospital_files: list[ClaimPDF]


@contextmanager
def _connection():
    with open_local_database() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                sum_insured INTEGER CHECK (sum_insured > 0)
            );
            CREATE TABLE IF NOT EXISTS claim_documents (
                claim_id INTEGER NOT NULL REFERENCES claims(id),
                position INTEGER NOT NULL CHECK (position >= 0),
                filename TEXT NOT NULL,
                pdf BLOB NOT NULL,
                storage_key TEXT,
                content_sha256 TEXT,
                PRIMARY KEY (claim_id, position)
            );
        """)
        if isinstance(connection, sqlite3.Connection):
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(claim_documents)")}
            if "storage_key" not in columns:
                connection.execute("ALTER TABLE claim_documents ADD COLUMN storage_key TEXT")
            if "content_sha256" not in columns:
                connection.execute("ALTER TABLE claim_documents ADD COLUMN content_sha256 TEXT")
        yield connection


def list_claims() -> dict[int, str]:
    with _connection() as connection:
        return {
            row["id"]: row["name"]
            for row in connection.execute("SELECT id, name FROM claims ORDER BY id DESC")
        }


def list_saved_policies():
    with _connection() as connection:
        rows = connection.execute("""
            SELECT policy.id, policy.name, policy.content_sha256, policy.pdf, claims.name AS source_claim
            FROM (
                SELECT min(claim_id) AS id, filename AS name, content_sha256, pdf
                FROM claim_documents
                WHERE position = 0
                GROUP BY filename, content_sha256, pdf
            ) AS policy
            JOIN claims ON claims.id = policy.id
            ORDER BY policy.name, policy.id
        """)
        policies = {}
        for row in rows:
            digest = row["content_sha256"] or sha256(row["pdf"]).hexdigest()
            policies.setdefault((row["name"], digest), {
                "id": row["id"], "name": row["name"], "source_claim": row["source_claim"],
            })
        return list(policies.values())


def load_saved_policy(policy_id: int) -> ClaimPDF | None:
    with _connection() as connection:
        row = connection.execute("""
            SELECT filename, pdf, storage_key, content_sha256 FROM claim_documents
            WHERE claim_id = ? AND position = 0
        """, (policy_id,)).fetchone()
        return _load_document(row) if row else None


def save_claim(claim: SavedClaim) -> int:
    if not claim.name.strip() or not (claim.hospital_files or claim.policy):
        raise ValueError("Enter a claim name and upload at least one PDF.")
    # Position zero holds the optional policy. Hospital PDFs keep upload order.
    files = list(enumerate(claim.hospital_files, start=1))
    if claim.policy is not None:
        files.insert(0, (0, claim.policy))
    for _, file in files:
        _validate_pdf(file)

    with _connection() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        claim_id = connection.execute(
            "INSERT INTO claims (name, sum_insured) VALUES (?, ?)",
            (claim.name.strip(), claim.sum_insured),
        ).lastrowid
        _insert_documents(connection, claim_id, files)
        return claim_id


def _validate_pdf(file):
    try:
        with pymupdf.open(stream=file.content, filetype="pdf") as pdf:
            if not pdf.is_pdf or pdf.needs_pass or not len(pdf):
                raise ValueError
    except (RuntimeError, ValueError):
        raise ValueError(f"Upload a readable, unlocked PDF for {file.name}.") from None


def _document_path(key):
    if not _DOCUMENT_KEY.fullmatch(key):
        raise OSError("Invalid document storage location.")
    configured = os.environ.get("CLAIMS_DOCUMENT_DIR")
    root = (Path(configured).expanduser() if configured else local_data_directory() / "documents").resolve()
    public = (Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
    if root.is_relative_to(public):
        raise OSError("Document storage must be outside the public frontend directory.")
    path = root / key
    if path.is_symlink():
        raise OSError("Invalid document storage location.")
    return path


def _load_document(row):
    key = row["storage_key"]
    if not key:
        return ClaimPDF(row["filename"], row["pdf"])
    content = _document_path(key).read_bytes()
    if sha256(content).hexdigest() != row["content_sha256"]:
        raise OSError("Document integrity check failed.")
    return ClaimPDF(row["filename"], content, key)


def _insert_documents(connection, claim_id, files):
    created = []
    rows = []
    try:
        for position, file in files:
            # A previously selected policy may have been deleted before this
            # transaction acquired the customer lock. Recreate it from its bytes.
            reusable = file.storage_key and _document_path(file.storage_key).is_file()
            key = file.storage_key if reusable else f"{uuid4().hex}.pdf"
            if not reusable:
                path = _document_path(key)
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    created.append(path)
                    output.write(file.content)
                    output.flush()
                    os.fsync(output.fileno())
            rows.append((claim_id, position, file.name, b"", key, sha256(file.content).hexdigest()))
        connection.executemany("""
            INSERT INTO claim_documents (claim_id, position, filename, pdf, storage_key, content_sha256)
            VALUES (?, ?, ?, ?, ?, ?)
        """, rows)
    except Exception:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def append_claim_documents(claim_id, policy, hospital_files):
    """Attach new files without changing the existing document positions."""
    if not policy and not hospital_files:
        raise ValueError("Select at least one PDF.")
    for file in ([policy] if policy else []) + hospital_files:
        _validate_pdf(file)
    with _connection() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        claim = connection.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if claim is None:
            return False
        positions = [row["position"] for row in connection.execute(
            "SELECT position FROM claim_documents WHERE claim_id = ?", (claim_id,)
        )]
        if policy and 0 in positions:
            raise ValueError("This claim already has a policy. Start a new claim for a different policy.")
        if sum(position > 0 for position in positions) + len(hospital_files) > 12:
            raise ValueError("Upload up to 12 hospital PDFs per claim.")
        new_files = list(enumerate(hospital_files, start=max(positions, default=0) + 1))
        if policy:
            new_files.insert(0, (0, policy))
        _insert_documents(connection, claim_id, new_files)
        return True


def delete_claim(claim_id: int) -> dict | None:
    """Delete an owned claim and remove unreferenced stored PDFs when possible."""
    with _connection() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        claim = connection.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if claim is None:
            return None
        keys = [row["storage_key"] for row in connection.execute(
            "SELECT storage_key FROM claim_documents WHERE claim_id = ?", (claim_id,)
        ) if row["storage_key"]]
        connection.execute("DELETE FROM claims WHERE id = ?", (claim_id,))

    # Serialize reference checks and file removal with document attachment.
    # Shared policy files stay available for other claims of this customer.
    cleanup_pending = False
    with _connection() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        for key in set(keys):
            referenced = connection.execute(
                "SELECT 1 FROM claim_documents WHERE storage_key = ? LIMIT 1", (key,)
            ).fetchone()
            if not referenced:
                try:
                    _document_path(key).unlink(missing_ok=True)
                except OSError:
                    cleanup_pending = True
    return {"deleted": True, "file_cleanup_pending": cleanup_pending}


def load_claim(claim_id: int) -> SavedClaim | None:
    with _connection() as connection:
        claim = connection.execute(
            "SELECT name, sum_insured FROM claims WHERE id = ?", (claim_id,)
        ).fetchone()
        if claim is None:
            return None
        rows = connection.execute("""
            SELECT position, filename, pdf, storage_key, content_sha256 FROM claim_documents
            WHERE claim_id = ?
            ORDER BY position
        """, (claim_id,))
        policy = None
        hospital_files = []
        for row in rows:
            file = _load_document(row)
            if row["position"] == 0:
                policy = file
            else:
                hospital_files.append(file)
        return SavedClaim(claim["name"], claim["sum_insured"], policy, hospital_files)
