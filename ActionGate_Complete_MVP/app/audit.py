"""Local append-only API for a tamper-evident (not tamper-proof) audit chain.

Hash chains detect event edits and reordering, but cannot prevent a privileged
party from deleting or truncating the tail of the local SQLite database.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping


@dataclass(frozen=True)
class AuditVerification:
    valid: bool
    event_count: int
    reason: str = ""


def ensure_audit_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL
        )
        """
    )


def append_event(connection: sqlite3.Connection, event_type: str, payload: Mapping[str, object]) -> int:
    """Append a canonical event. Callers must not put secrets in *payload*."""
    if not event_type or len(event_type) > 64:
        raise ValueError("event type must be a non-empty string up to 64 characters")
    ensure_audit_table(connection)
    payload_json = _canonical_json(payload)
    previous = connection.execute(
        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    previous_hash = "" if previous is None else str(previous[0])
    created_at = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        "INSERT INTO audit_events (event_type, payload_json, created_at, previous_hash, event_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (event_type, payload_json, created_at, previous_hash, "pending"),
    )
    sequence = int(cursor.lastrowid)
    event_hash = _event_hash(sequence, event_type, payload_json, created_at, previous_hash)
    connection.execute("UPDATE audit_events SET event_hash = ? WHERE sequence = ?", (event_hash, sequence))
    return sequence


def verify_chain(connection: sqlite3.Connection) -> AuditVerification:
    ensure_audit_table(connection)
    previous_hash = ""
    rows = connection.execute(
        "SELECT sequence, event_type, payload_json, created_at, previous_hash, event_hash "
        "FROM audit_events ORDER BY sequence"
    ).fetchall()
    for sequence, event_type, payload_json, created_at, stored_previous, event_hash in rows:
        if stored_previous != previous_hash:
            return AuditVerification(False, len(rows), f"previous hash mismatch at event {sequence}")
        expected = _event_hash(sequence, event_type, payload_json, created_at, stored_previous)
        if event_hash != expected:
            return AuditVerification(False, len(rows), f"event hash mismatch at event {sequence}")
        previous_hash = event_hash
    return AuditVerification(True, len(rows))


def list_events(connection: sqlite3.Connection) -> list[dict[str, object]]:
    ensure_audit_table(connection)
    rows = connection.execute(
        "SELECT sequence, event_type, payload_json, created_at, event_hash FROM audit_events ORDER BY sequence"
    ).fetchall()
    return [
        {"sequence": row[0], "event_type": row[1], "payload": json.loads(row[2]), "created_at": row[3], "hash": row[4]}
        for row in rows
    ]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_hash(sequence: int, event_type: str, payload_json: str, created_at: str, previous_hash: str) -> str:
    material = _canonical_json(
        {"sequence": sequence, "event_type": event_type, "payload": payload_json, "created_at": created_at, "previous_hash": previous_hash}
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
