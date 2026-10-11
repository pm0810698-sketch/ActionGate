"""Scope-bound, single-use local approval records."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .audit import append_event
from .impact import Impact, inspect_impact
from .policy import decide
from .schema import Action, SchemaValidationError, validate_action

POLICY_VERSION = "phase-1"


class ApprovalError(ValueError):
    """Raised when an approval cannot be created or used."""


@dataclass(frozen=True)
class Approval:
    approval_id: str
    action_digest: str
    impact_digest: str
    impact_row_count: int
    policy_version: str
    requester: str
    approver: str
    expires_at: str
    consumed_at: str | None = None


def ensure_approval_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            action_digest TEXT NOT NULL,
            impact_digest TEXT NOT NULL,
            impact_row_count INTEGER NOT NULL,
            policy_version TEXT NOT NULL,
            requester TEXT NOT NULL,
            approver TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT
        )
        """
    )


def action_digest(action: Action) -> str:
    validated = validate_action(action.to_payload())
    encoded = json.dumps(validated.to_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_approval(
    database_path: str | Path,
    action: Action,
    impact: Impact,
    approver: str,
    expires_at: datetime,
    policy_version: str = POLICY_VERSION,
) -> Approval:
    """Create an approval only for a held action with verified current impact."""
    try:
        action = validate_action(action.to_payload())
    except (SchemaValidationError, AttributeError, TypeError) as error:
        raise ApprovalError(f"invalid action: {error}") from error

    if not isinstance(approver, str) or not approver.strip():
        raise ApprovalError("approver must be a non-requester identity")
    approver = approver.strip()
    if approver == action.requested_by:
        raise ApprovalError("approver must be a non-requester identity")
    if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
        raise ApprovalError("expiry must be timezone-aware")
    expiry = expires_at.astimezone(UTC)
    if expiry <= datetime.now(UTC):
        raise ApprovalError("approval expiry must be in the future")
    if policy_version != POLICY_VERSION:
        raise ApprovalError("unsupported approval policy version")

    actual_impact = inspect_impact(database_path, action)
    if not actual_impact.reliable:
        raise ApprovalError("reliable database impact is required")
    if not isinstance(impact, Impact) or (
        not impact.reliable
        or impact.digest != actual_impact.digest
        or impact.row_count != actual_impact.row_count
        or impact.primary_keys != actual_impact.primary_keys
    ):
        raise ApprovalError("supplied impact does not match current database impact")
    if decide(action, actual_impact).outcome != "HOLD":
        raise ApprovalError("only held actions can be approved")

    approval = Approval(
        approval_id=str(uuid.uuid4()),
        action_digest=action_digest(action),
        impact_digest=actual_impact.digest,
        impact_row_count=actual_impact.row_count,
        policy_version=POLICY_VERSION,
        requester=action.requested_by,
        approver=approver,
        expires_at=expiry.isoformat(),
    )
    with sqlite3.connect(database_path) as connection:
        ensure_approval_table(connection)
        connection.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (approval.approval_id, approval.action_digest, approval.impact_digest,
             approval.impact_row_count, approval.policy_version, approval.requester,
             approval.approver, approval.expires_at),
        )
        append_event(connection, "approval_created", {
            "approval_id": approval.approval_id,
            "requester": approval.requester,
            "approver": approval.approver,
            "action_digest": approval.action_digest,
            "impact_digest": approval.impact_digest,
            "impact_row_count": approval.impact_row_count,
            "policy_version": approval.policy_version,
            "expires_at": approval.expires_at,
        })
    return approval


def consume_approval(
    connection: sqlite3.Connection,
    approval_id: str | None,
    action: Action,
    impact: Impact,
    policy_version: str = POLICY_VERSION,
) -> None:
    """Validate and atomically consume an approval inside the caller's transaction."""
    if not approval_id:
        raise ApprovalError("a held action requires an approval")
    ensure_approval_table(connection)
    row = connection.execute(
        "SELECT action_digest, impact_digest, impact_row_count, policy_version, requester, expires_at, consumed_at "
        "FROM approvals WHERE approval_id = ?", (approval_id,)
    ).fetchone()
    if row is None:
        raise ApprovalError("unknown approval")
    expected_action, expected_impact, expected_count, expected_version, requester, expires_at, consumed_at = row
    if consumed_at is not None:
        raise ApprovalError("approval has already been consumed")
    if requester != action.requested_by or expected_action != action_digest(action):
        raise ApprovalError("approval does not match action")
    if expected_impact != impact.digest or expected_count != impact.row_count:
        raise ApprovalError("approval does not match current impact")
    if expected_version != policy_version:
        raise ApprovalError("approval policy version does not match")
    if datetime.fromisoformat(expires_at) <= datetime.now(UTC):
        raise ApprovalError("approval has expired")
    consumed_at = datetime.now(UTC).isoformat()
    updated = connection.execute(
        "UPDATE approvals SET consumed_at = ? WHERE approval_id = ? AND consumed_at IS NULL",
        (consumed_at, approval_id),
    ).rowcount
    if updated != 1:
        raise ApprovalError("approval could not be consumed")
