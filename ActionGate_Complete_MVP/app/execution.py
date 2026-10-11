"""Transactional execution of allowlisted local demo actions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .approval import ApprovalError, POLICY_VERSION, consume_approval
from .audit import append_event
from .database import where_clause
from .impact import Impact, inspect_impact_connection
from .policy import Decision, decide
from .schema import Action, SchemaValidationError, validate_action


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    reason: str
    decision: Decision
    impact: Impact | None
    affected_primary_keys: tuple[int, ...] = ()
    rows: tuple[tuple[object, ...], ...] = ()


def execute_action(database_path: str | Path, action: Action, approval_id: str | None = None) -> ExecutionResult:
    """Revalidate, recompute impact, consume approval, and execute atomically."""
    connection = sqlite3.connect(database_path, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            action = validate_action(action.to_payload())
            impact = inspect_impact_connection(connection, action)
        except (SchemaValidationError, AttributeError, sqlite3.Error, ValueError) as error:
            decision = Decision("BLOCK", f"invalid execution input: {error}")
            append_event(connection, "execution_refused", {"reason": decision.reason})
            connection.commit()
            return ExecutionResult(False, decision.reason, decision, None)
        decision = decide(action, impact)
        append_event(connection, "execution_attempt", {"request_id": action.request_id, "decision": decision.outcome, "impact_digest": impact.digest})
        if decision.outcome == "BLOCK":
            append_event(connection, "execution_refused", {"request_id": action.request_id, "reason": decision.reason})
            connection.commit()
            return ExecutionResult(False, decision.reason, decision, impact)
        if decision.outcome == "HOLD":
            try:
                consume_approval(connection, approval_id, action, impact, POLICY_VERSION)
            except ApprovalError as error:
                append_event(connection, "execution_refused", {"request_id": action.request_id, "reason": str(error)})
                connection.commit()
                return ExecutionResult(False, str(error), decision, impact)
        if action.operation == "SELECT":
            where_sql, parameters = where_clause(action.filters)
            query = f"SELECT {', '.join(action.columns)} FROM {action.table}{where_sql}"
            rows = tuple(tuple(row) for row in connection.execute(query, parameters))
            append_event(connection, "execution_succeeded", {"request_id": action.request_id, "row_count": len(rows)})
            connection.commit()
            return ExecutionResult(True, "read completed", decision, impact, impact.primary_keys, rows)
        if action.operation == "UPDATE":
            assignments = ", ".join(f"{column} = ?" for column, _ in action.set_values)
            values = tuple(value for _, value in action.set_values)
            where_sql, parameters = where_clause(action.filters)
            cursor = connection.execute(f"UPDATE {action.table} SET {assignments}{where_sql}", values + parameters)
            if cursor.rowcount != impact.row_count:
                raise sqlite3.DatabaseError("updated row count differs from inspected impact")
            append_event(connection, "execution_succeeded", {"request_id": action.request_id, "row_count": cursor.rowcount})
            connection.commit()
            return ExecutionResult(True, "mutation completed", decision, impact, impact.primary_keys)
        raise sqlite3.DatabaseError("unsupported validated operation")
    except Exception as error:
        connection.rollback()
        decision = Decision("BLOCK", "execution transaction failed")
        return ExecutionResult(False, str(error), decision, None)
    finally:
        connection.close()
