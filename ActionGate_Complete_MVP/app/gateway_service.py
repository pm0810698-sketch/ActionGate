"""ActionGate's local HTTP authorization gateway.

This process is the only component the demo agent calls. It interprets requests,
validates impact, applies policy, handles approval, and invokes allowlisted tools.
It intentionally exposes no shell/SQL/eval endpoint and binds to loopback by default.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .approval import ApprovalError, action_digest, create_approval
from .audit import append_event, list_events, verify_chain
from .database import initialize_demo_database
from .execution import execute_action
from .external_tools import (
    ToolPlan,
    create_tool_approval,
    decision_for_tool,
    execute_tool_plan,
    inspect_tool_plan,
    interpret_tool_task,
    should_route_external_task,
)
from .impact import inspect_impact
from .interpreter import interpret_task
from .policy import decide
from .schema import Action, validate_action


def database_path() -> Path:
    configured = os.getenv("ACTIONGATE_DATABASE", "").strip()
    return Path(configured).expanduser().resolve() if configured else (Path("data") / "actiongate_demo.db").resolve()


def _json_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_payload(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass
class PendingRequest:
    request_id: str
    kind: str
    source: str
    status: str
    task_digest: str
    message: str
    outcome: str
    reason: str
    action_payload: dict[str, Any] | None = None
    tool_payload: dict[str, Any] | None = None
    impact_digest: str = ""
    impact_row_count: int = 0
    impact_summary: str = ""
    impact_details: dict[str, Any] | None = None
    impact_reliable: bool = False
    approval_id: str | None = None
    completed: bool = False


class GatewayService:
    """Stateful gateway used by the HTTP adapter and test suite."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or database_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        initialize_demo_database(self.db_path)
        self._requests: dict[str, PendingRequest] = {}
        self._lock = threading.RLock()

    def _audit(self, event_type: str, payload: dict[str, object]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            append_event(conn, event_type, payload)

    def health(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            verification = verify_chain(conn)
        return {
            "service": "ActionGate Gateway",
            "status": "ok",
            "policy": "deterministic fail-closed",
            "audit_chain_valid": verification.valid,
            "audit_event_count": verification.event_count,
            "mode": "local demo; bind to loopback; demo identities are not authenticated",
        }

    def inspect_task(self, payload: object) -> dict[str, Any]:
        data = _safe_payload(payload)
        task = data.get("task")
        requester = data.get("requester", "demo_requester")
        force_fallback = data.get("force_fallback", False)
        if not isinstance(task, str):
            return {"ok": False, "error": "task must be a string"}
        if not isinstance(requester, str) or not requester.strip() or len(requester) > 128:
            return {"ok": False, "error": "requester must be a non-empty string up to 128 characters"}
        if not isinstance(force_fallback, bool):
            return {"ok": False, "error": "force_fallback must be boolean"}

        task = task.strip()
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        digest = hashlib.sha256(task.encode("utf-8", errors="replace")).hexdigest()
        self._audit("gateway_task_received", {
            "request_id": request_id, "requester": requester.strip(),
            "task_digest": digest, "task_length": len(task),
        })

        try:
            if should_route_external_task(task):
                interpreted = interpret_tool_task(
                    task, request_id=request_id, requester=requester.strip(), force_fallback=force_fallback
                )
                if interpreted.plan is None:
                    pending = PendingRequest(
                        request_id, "tool", interpreted.source, interpreted.status, interpreted.task_digest,
                        interpreted.message, "BLOCK", interpreted.message,
                    )
                    self._store(pending)
                    self._audit("gateway_interpreter_result", {
                        "request_id": request_id, "decision_source": interpreted.source,
                        "interpretation_status": interpreted.status, "task_digest": digest,
                    })
                    self._audit("gateway_decision", {
                        "request_id": request_id, "outcome": "BLOCK", "reason": interpreted.message,
                        "decision_source": interpreted.source,
                    })
                    return self._public(pending)

                plan = interpreted.plan
                inspection = inspect_tool_plan(plan)
                outcome, reason = decision_for_tool(plan, inspection)
                pending = PendingRequest(
                    request_id=request_id, kind="tool", source=interpreted.source,
                    status=interpreted.status, task_digest=interpreted.task_digest,
                    message=interpreted.message, outcome=outcome, reason=reason,
                    tool_payload=plan.to_payload(), impact_digest=inspection.digest,
                    impact_row_count=inspection.row_count, impact_summary=inspection.summary,
                    impact_details=inspection.details, impact_reliable=inspection.reliable,
                )
                self._store(pending)
                self._audit("gateway_interpreter_result", {
                    "request_id": request_id, "decision_source": interpreted.source,
                    "interpretation_status": interpreted.status, "task_digest": digest,
                    "model": interpreted.model,
                })
                self._audit("gateway_decision", {
                    "request_id": request_id, "outcome": outcome, "reason": reason,
                    "decision_source": interpreted.source, "tool": plan.tool,
                    "action_digest": _json_digest(plan.to_payload()),
                    "impact_digest": inspection.digest, "impact_row_count": inspection.row_count,
                })
                return self._public(pending)

            interpreted = interpret_task(
                task, request_id=request_id, requested_by=requester.strip(), force_fallback=force_fallback
            )
            if interpreted.action is None:
                pending = PendingRequest(
                    request_id, "database", interpreted.source, interpreted.status,
                    interpreted.task_digest, interpreted.message, "BLOCK", interpreted.message,
                )
                self._store(pending)
                self._audit("gateway_interpreter_result", {
                    "request_id": request_id, "decision_source": interpreted.source,
                    "interpretation_status": interpreted.status, "task_digest": digest,
                    "model": interpreted.model,
                })
                self._audit("gateway_decision", {
                    "request_id": request_id, "outcome": "BLOCK", "reason": interpreted.message,
                    "decision_source": interpreted.source,
                })
                return self._public(pending)

            action = interpreted.action
            impact = inspect_impact(self.db_path, action)
            decision = decide(action, impact)
            pending = PendingRequest(
                request_id=request_id, kind="database", source=interpreted.source,
                status=interpreted.status, task_digest=interpreted.task_digest,
                message=interpreted.message, outcome=decision.outcome, reason=decision.reason,
                action_payload=action.to_payload(), impact_digest=impact.digest,
                impact_row_count=impact.row_count,
                impact_summary="Database-derived affected primary keys",
                impact_details={"primary_keys": list(impact.primary_keys), "reliable": impact.reliable},
                impact_reliable=impact.reliable,
            )
            self._store(pending)
            self._audit("gateway_interpreter_result", {
                "request_id": request_id, "decision_source": interpreted.source,
                "interpretation_status": interpreted.status, "task_digest": digest,
                "model": interpreted.model,
            })
            self._audit("gateway_decision", {
                "request_id": request_id, "outcome": decision.outcome,
                "reason": decision.reason, "decision_source": interpreted.source,
                "action_digest": action_digest(action), "impact_digest": impact.digest,
                "impact_row_count": impact.row_count, "agent_id": action.agent_id,
                "operation": action.operation, "table": action.table,
            })
            return self._public(pending)
        except Exception as error:
            # Fail closed; never return stack traces or credentials to the client.
            self._audit("gateway_internal_failure", {
                "request_id": request_id, "error_type": type(error).__name__,
            })
            pending = PendingRequest(
                request_id, "unknown", "gateway_error", "BLOCK", digest,
                "Gateway could not safely inspect the task.", "BLOCK",
                f"Gateway failure ({type(error).__name__}); no action was executed.",
            )
            self._store(pending)
            self._audit("gateway_decision", {
                "request_id": request_id, "outcome": "BLOCK",
                "reason": pending.reason, "decision_source": "gateway_error",
            })
            return self._public(pending)

    def approve(self, payload: object) -> dict[str, Any]:
        data = _safe_payload(payload)
        request_id = data.get("request_id")
        reviewer = data.get("reviewer")
        if not isinstance(request_id, str) or not isinstance(reviewer, str) or not reviewer.strip():
            return {"ok": False, "error": "request_id and reviewer are required"}
        with self._lock:
            pending = self._requests.get(request_id)
        if pending is None:
            return {"ok": False, "error": "Unknown or expired in-memory request. Submit it again."}
        if pending.completed:
            return {"ok": False, "error": "Request already completed."}
        if pending.outcome != "HOLD":
            return {"ok": False, "error": "Only HOLD requests can be approved."}
        try:
            if pending.kind == "database":
                action = validate_action(pending.action_payload or {})
                current = inspect_impact(self.db_path, action)
                if not current.reliable or current.digest != pending.impact_digest or current.row_count != pending.impact_row_count:
                    self._record_refusal(pending, "Impact changed before approval; submit and inspect a new request.")
                    return {"ok": False, "error": "Impact changed before approval; submit and inspect a new request."}
                approval = create_approval(
                    self.db_path, action, current, reviewer,
                    datetime.now(UTC) + timedelta(minutes=5),
                )
                approval_id = approval.approval_id
            elif pending.kind == "tool":
                plan = ToolPlan(**(pending.tool_payload or {}))
                current = inspect_tool_plan(plan)
                if not current.reliable or current.digest != pending.impact_digest or current.row_count != pending.impact_row_count:
                    self._record_refusal(pending, "Impact changed before approval; submit and inspect a new request.")
                    return {"ok": False, "error": "Impact changed before approval; submit and inspect a new request."}
                approval_id = create_tool_approval(self.db_path, plan, current, reviewer)
            else:
                return {"ok": False, "error": "Unsupported request kind."}
            with self._lock:
                pending.approval_id = approval_id
            self._audit("gateway_approval_issued", {
                "request_id": request_id, "approval_id": approval_id,
                "approver": reviewer.strip(), "action_digest": _json_digest(pending.action_payload or pending.tool_payload),
                "impact_digest": pending.impact_digest,
            })
            return {"ok": True, "request_id": request_id, "approval_id": approval_id, "expires_in_seconds": 300}
        except (ApprovalError, ValueError) as error:
            return {"ok": False, "error": str(error)}
        except Exception as error:
            self._audit("gateway_approval_failure", {"request_id": request_id, "error_type": type(error).__name__})
            return {"ok": False, "error": f"Approval could not be created ({type(error).__name__})."}

    def execute(self, payload: object) -> dict[str, Any]:
        data = _safe_payload(payload)
        request_id = data.get("request_id")
        approval_id = data.get("approval_id")
        confirmed = data.get("confirmed", False)
        if not isinstance(request_id, str) or not isinstance(confirmed, bool):
            return {"ok": False, "error": "request_id and boolean confirmed are required"}
        with self._lock:
            pending = self._requests.get(request_id)
        if pending is None:
            return {"ok": False, "error": "Unknown in-memory request. Submit the task again."}
        if pending.completed:
            return {"ok": False, "error": "Request already completed; replay is rejected."}
        if pending.outcome == "BLOCK":
            return {"ok": False, "error": "BLOCKED requests cannot execute."}
        if pending.outcome == "HOLD":
            if not pending.approval_id or approval_id != pending.approval_id:
                return {"ok": False, "error": "The matching one-time approval is required."}
            if not confirmed:
                return {"ok": False, "error": "Explicit execution confirmation is required."}

        try:
            if pending.kind == "database":
                action = validate_action(pending.action_payload or {})
                current = inspect_impact(self.db_path, action)
                if not current.reliable or current.digest != pending.impact_digest or current.row_count != pending.impact_row_count:
                    self._record_refusal(pending, "Impact drift detected. Reinspect and reauthorize.")
                    return {"ok": False, "error": "Impact drift detected. Reinspect and reauthorize."}
                result = execute_action(self.db_path, action, approval_id if pending.outcome == "HOLD" else None)
                execution_status = "SUCCEEDED" if result.success else "FAILED"
                response = {
                    "ok": result.success,
                    "request_id": request_id,
                    # Keep the authorization decision distinct from execution status:
                    # a HOLD can become a successful execution after approval.
                    "authorization_decision": pending.outcome,
                    "execution_status": execution_status,
                    "outcome": execution_status,
                    "message": result.reason,
                    "affected_primary_keys": list(result.affected_primary_keys),
                    "rows": [list(row) for row in result.rows],
                }
                if result.success:
                    pending.completed = True
                self._audit("gateway_execution_result", {
                    "request_id": request_id,
                    "success": result.success,
                    "decision_source": pending.source,
                    "authorization_decision": pending.outcome,
                    "execution_status": execution_status,
                    "reason": result.reason,
                    "affected_row_count": len(result.affected_primary_keys),
                })
                return response

            if pending.kind == "tool":
                plan = ToolPlan(**(pending.tool_payload or {}))
                current = inspect_tool_plan(plan)
                if not current.reliable or current.digest != pending.impact_digest or current.row_count != pending.impact_row_count:
                    self._record_refusal(pending, "Impact drift detected. Reinspect and reauthorize.")
                    return {"ok": False, "error": "Impact drift detected. Reinspect and reauthorize."}
                result = execute_tool_plan(
                    self.db_path, plan, current,
                    approval_id=approval_id if pending.outcome == "HOLD" else None,
                    explicitly_confirmed=confirmed,
                )
                execution_status = "SUCCEEDED" if result.success else "FAILED"
                response = {
                    "ok": result.success,
                    "request_id": request_id,
                    "authorization_decision": pending.outcome,
                    "execution_status": execution_status,
                    "outcome": execution_status,
                    "message": result.message,
                    "details": result.details,
                }
                if result.success:
                    pending.completed = True
                self._audit("gateway_execution_result", {
                    "request_id": request_id,
                    "success": result.success,
                    "decision_source": pending.source,
                    "authorization_decision": pending.outcome,
                    "execution_status": execution_status,
                    "reason": result.message,
                })
                return response
            return {"ok": False, "error": "Unsupported request kind."}
        except Exception as error:
            self._audit("gateway_execution_failure", {"request_id": request_id, "error_type": type(error).__name__})
            return {"ok": False, "error": f"Execution failed safely ({type(error).__name__})."}

    def events(self, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        with sqlite3.connect(self.db_path) as conn:
            verification = verify_chain(conn)
            records = list_events(conn)
        return {"ok": True, "chain_valid": verification.valid, "event_count": verification.event_count, "events": records[-limit:]}

    def _record_refusal(self, pending: PendingRequest, reason: str) -> None:
        self._audit("gateway_execution_refused", {
            "request_id": pending.request_id, "outcome": "BLOCK",
            "reason": reason, "decision_source": pending.source,
        })

    def _store(self, pending: PendingRequest) -> None:
        with self._lock:
            self._requests[pending.request_id] = pending

    @staticmethod
    def _public(p: PendingRequest) -> dict[str, Any]:
        return {
            "ok": True,
            "request_id": p.request_id,
            "kind": p.kind,
            "interpretation": {
                "source": p.source, "status": p.status,
                "message": p.message, "task_digest": p.task_digest,
            },
            "decision": {"outcome": p.outcome, "reason": p.reason},
            "proposal": p.action_payload if p.kind == "database" else p.tool_payload,
            "impact": {
                "reliable": p.impact_reliable,
                "digest": p.impact_digest,
                "row_count": p.impact_row_count,
                "summary": p.impact_summary,
                "details": p.impact_details or {},
            },
            "approval_required": p.outcome == "HOLD",
            "completed": p.completed,
        }
