from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.approval import ApprovalError, create_approval
from app.database import initialize_demo_database
from app.execution import execute_action
from app.impact import inspect_impact
from app.policy import MAX_UPDATE_ROWS, decide
from app.schema import validate_action


def update_action(status: str = "review"):
    return validate_action(
        {
            "request_id": "update-101",
            "agent_id": "operations_agent",
            "operation": "UPDATE",
            "table": "orders",
            "columns": ["order_id", "status"],
            "filters": [{"column": "order_id", "operator": "eq", "value": 101}],
            "set_values": {"status": status},
            "requested_by": "requester",
        }
    )


def approved_update(database, action=None):
    action = action or update_action()
    impact = inspect_impact(database, action)
    return action, create_approval(database, action, impact, "reviewer", datetime.now(UTC) + timedelta(minutes=5))


def test_self_approval_and_expiry_are_rejected(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action = update_action()
    impact = inspect_impact(database, action)
    with pytest.raises(ApprovalError, match="non-requester"):
        create_approval(database, action, impact, "requester", datetime.now(UTC) + timedelta(minutes=5))
    with pytest.raises(ApprovalError, match="future"):
        create_approval(database, action, impact, "reviewer", datetime.now(UTC) - timedelta(minutes=1))


def test_self_approval_rejects_whitespace_variations(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action = validate_action({
        "request_id": "update-101", "agent_id": "operations_agent", "operation": "UPDATE",
        "table": "orders", "columns": ["order_id", "status"],
        "filters": [{"column": "order_id", "operator": "eq", "value": 101}],
        "set_values": {"status": "review"}, "requested_by": " alice ",
    })
    assert action.requested_by == "alice"
    impact = inspect_impact(database, action)
    with pytest.raises(ApprovalError, match="non-requester"):
        create_approval(database, action, impact, "alice ", datetime.now(UTC) + timedelta(minutes=5))


def test_approver_identity_is_trimmed(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action = update_action()
    impact = inspect_impact(database, action)
    approval = create_approval(database, action, impact, "  reviewer  ", datetime.now(UTC) + timedelta(minutes=5))
    assert approval.approver == "reviewer"


def test_approval_replay_and_action_tampering_are_rejected(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action, approval = approved_update(database)
    altered_payload = action.to_payload()
    altered_payload["filters"] = [{"column": "order_id", "operator": "eq", "value": 102}]
    altered = validate_action(altered_payload)
    tampered = execute_action(database, altered, approval.approval_id)
    assert not tampered.success and "does not match action" in tampered.reason
    first = execute_action(database, action, approval.approval_id)
    assert first.success
    replay = execute_action(database, action, approval.approval_id)
    assert not replay.success and "already been consumed" in replay.reason


def test_impact_drift_and_policy_version_mismatch_are_rejected(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action, approval = approved_update(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE orders SET order_id = 104 WHERE order_id = 101")
    result = execute_action(database, action, approval.approval_id)
    assert not result.success and "current impact" in result.reason

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE orders SET order_id = 101 WHERE order_id = 104")
    action, approval = approved_update(database, update_action("review"))
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE approvals SET policy_version = 'old' WHERE approval_id = ?", (approval.approval_id,))
    result = execute_action(database, action, approval.approval_id)
    assert not result.success and "policy version" in result.reason


def test_blocked_action_does_not_mutate_and_update_rolls_back_on_failure(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action = update_action()
    blocked = execute_action(database, action)
    assert not blocked.success and "requires an approval" in blocked.reason
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM orders WHERE order_id = 101").fetchone()[0] == "pending"

    action, approval = approved_update(database)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TRIGGER force_failure BEFORE UPDATE ON orders BEGIN SELECT RAISE(ABORT, 'forced update failure'); END")
    failed = execute_action(database, action, approval.approval_id)
    assert not failed.success
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT consumed_at FROM approvals WHERE approval_id = ?", (approval.approval_id,)).fetchone()[0] is None
        assert connection.execute("SELECT status FROM orders WHERE order_id = 101").fetchone()[0] == "pending"


def test_approved_mutation_executes_and_allow_read_needs_no_approval(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    action, approval = approved_update(database)
    result = execute_action(database, action, approval.approval_id)
    assert result.success and result.affected_primary_keys == (101,)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM orders WHERE order_id = 101").fetchone()[0] == "review"
    read = validate_action({
        "request_id": "read-1", "agent_id": "support_agent", "operation": "SELECT", "table": "customers",
        "columns": ["customer_id", "name"], "filters": [], "requested_by": "requester",
    })
    assert execute_action(database, read).success


def test_excessive_update_is_blocked_without_mutation(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO orders (order_id, customer_id, status, total_cents) VALUES (?, ?, ?, ?)",
            [(200 + i, 1, "pending", 1000) for i in range(MAX_UPDATE_ROWS + 1)],
        )
    action = validate_action({
        "request_id": "update-too-many", "agent_id": "operations_agent", "operation": "UPDATE",
        "table": "orders", "columns": ["order_id", "status"],
        "filters": [{"column": "status", "operator": "eq", "value": "pending"}],
        "declared_impact_limit": 1000000, "set_values": {"status": "review"}, "requested_by": "requester",
    })
    impact = inspect_impact(database, action)
    assert impact.row_count > MAX_UPDATE_ROWS
    decision = decide(action, impact)
    assert decision.outcome == "BLOCK" and "server limit" in decision.reason
    result = execute_action(database, action)
    assert not result.success
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders WHERE status = 'review'").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0] == MAX_UPDATE_ROWS + 2
