"""Persist reimbursement estimate revisions and their reviewed inputs."""

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal

from backend.documents.bill_items import BillItem
from backend.claims.claim_estimate import ClaimEstimate, CopaymentRule, ReviewedDeduction
from backend.storage.local_database import open_local_database


@dataclass(frozen=True)
class EstimateSnapshot:
    estimate: ClaimEstimate
    remaining_cover: Decimal
    bill_name: str
    net_bill_page: int
    policy_name: str
    copayment_rule: CopaymentRule


@dataclass(frozen=True)
class EstimateRevision:
    id: int
    saved_at: str
    snapshot: EstimateSnapshot


@contextmanager
def _connection():
    with open_local_database() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS claim_estimate_revisions (
                id INTEGER PRIMARY KEY,
                claim_id INTEGER NOT NULL REFERENCES claims(id),
                bill_hash TEXT NOT NULL,
                policy_hash TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS claim_estimates_by_document
            ON claim_estimate_revisions (claim_id, bill_hash, policy_hash, id)
        """)
        yield connection


def save_estimate(
    claim_id: int, bill_hash: str, policy_hash: str, snapshot: EstimateSnapshot,
) -> int:
    """Append a changed snapshot and leave the previous calculation intact."""
    payload = json.dumps(asdict(snapshot), default=lambda value: format(value.normalize(), "f"), sort_keys=True)
    identity = (claim_id, bill_hash, policy_hash)
    with _connection() as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute("""
            SELECT id, snapshot FROM claim_estimate_revisions
            WHERE claim_id = ? AND bill_hash = ? AND policy_hash = ?
            ORDER BY id DESC LIMIT 1
        """, identity).fetchone()
        if latest is not None and latest["snapshot"] == payload:
            return latest["id"]
        return connection.execute("""
            INSERT INTO claim_estimate_revisions (claim_id, bill_hash, policy_hash, snapshot)
            VALUES (?, ?, ?, ?)
        """, (*identity, payload)).lastrowid


def load_estimate_history(claim_id: int, bill_hash: str, policy_hash: str) -> list[EstimateRevision]:
    with _connection() as connection:
        rows = connection.execute("""
            SELECT id, saved_at, snapshot FROM claim_estimate_revisions
            WHERE claim_id = ? AND bill_hash = ? AND policy_hash = ?
            ORDER BY id DESC
        """, (claim_id, bill_hash, policy_hash))
        return [EstimateRevision(row["id"], row["saved_at"], _decode(row["snapshot"])) for row in rows]


def _decode(payload: str) -> EstimateSnapshot:
    data = json.loads(payload)
    rule = data.pop("copayment_rule")
    rule["percent"] = Decimal(rule["percent"])
    estimate = data.pop("estimate")
    deductions = []
    for deduction in estimate.pop("deductions"):
        item = deduction["item"]
        item["rate"] = Decimal(item["rate"])
        item["amount"] = Decimal(item["amount"])
        deductions.append(ReviewedDeduction(
            BillItem(**item), Decimal(deduction["amount"]), deduction["reason"],
        ))
    data["remaining_cover"] = Decimal(data["remaining_cover"])
    return EstimateSnapshot(
        **data,
        copayment_rule=CopaymentRule(**rule),
        estimate=ClaimEstimate(
            **{field: Decimal(value) for field, value in estimate.items()},
            deductions=tuple(deductions),
        ),
    )
