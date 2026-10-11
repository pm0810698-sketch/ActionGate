"""ActionGate local AI-agent authorization demo.

Run: python -m streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import streamlit as st

from app.approval import ApprovalError, action_digest, create_approval
from app.audit import append_event, list_events, verify_chain
from app.database import initialize_demo_database
from app.execution import execute_action
from app.impact import inspect_impact
from app.interpreter import interpret_task
from app.external_tools import (
    ToolPlan,
    create_tool_approval,
    decision_for_tool,
    execute_tool_plan,
    inspect_tool_plan,
    interpret_tool_task,
    should_route_external_task,
    workspace_root,
)
from app.policy import decide
from app.schema import Action, validate_action

DATABASE_PATH = Path("data") / "actiongate_demo.db"


def _ensure_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    initialize_demo_database(DATABASE_PATH)


def _append(event_type: str, payload: dict[str, object]) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        append_event(connection, event_type, payload)


def _audit_task_request(task: str, request_id: str, source: str, status: str, message: str) -> None:
    # Do not store the full raw prompt; store a digest for correlation.
    digest = hashlib.sha256(task.encode("utf-8", errors="replace")).hexdigest()
    _append("task_received", {
        "request_id": request_id,
        "task_digest": digest,
        "task_length": len(task),
        "requester": "demo_requester",
    })
    _append("interpreter_result", {
        "request_id": request_id,
        "decision_source": source,
        "interpretation_status": status,
        "message": message,
        "task_digest": digest,
    })


def _audit_decision(action: Action, source: str, outcome: str, reason: str, impact_digest: str, row_count: int) -> None:
    _append("decision_recorded", {
        "request_id": action.request_id,
        "agent_id": action.agent_id,
        "requester": action.requested_by,
        "operation": action.operation,
        "table": action.table,
        "action_digest": action_digest(action),
        "impact_digest": impact_digest,
        "impact_row_count": row_count,
        "outcome": outcome,
        "reason": reason,
        "decision_source": source,
    })


def _load_audit():
    with sqlite3.connect(DATABASE_PATH) as connection:
        return verify_chain(connection), list_events(connection)


def _event_summary(events):
    counts = {"ALLOW": 0, "HOLD": 0, "BLOCK": 0}
    for event in events:
        if event.get("event_type") in {"decision_recorded", "task_blocked"}:
            payload = event.get("payload", {})
            if isinstance(payload, dict) and payload.get("outcome") in counts:
                counts[str(payload["outcome"])] += 1
    return counts


def _decision_banner(outcome: str, reason: str) -> None:
    color = {"ALLOW": "#173b2b", "HOLD": "#3a2d16", "BLOCK": "#3b1c24"}.get(outcome, "#202938")
    edge = {"ALLOW": "#32b67a", "HOLD": "#e4a63a", "BLOCK": "#f06472"}.get(outcome, "#526275")
    st.markdown(
        f'<div style="background:{color};border:1px solid {edge};border-radius:10px;'
        f'padding:12px 14px;margin:8px 0 16px;color:#f1f5f9"><b>{outcome}</b> · {reason}</div>',
        unsafe_allow_html=True,
    )


def _render_events(events):
    rows = []
    for event in reversed(events[-100:]):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        rows.append({
            "#": event.get("sequence"),
            "Time (UTC)": event.get("created_at"),
            "Event": event.get("event_type"),
            "Request": payload.get("request_id", "—"),
            "Decision": payload.get("outcome", "—"),
            "Source": payload.get("decision_source", "—"),
            "Details": payload.get("reason", payload.get("message", payload.get("approver", "—"))),
        })
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No events yet. Start in Task Gateway to submit your first request.")


def _current_tool_plan() -> ToolPlan | None:
    payload = st.session_state.get("external_tool_plan")
    if not isinstance(payload, dict):
        return None
    try:
        return ToolPlan(**payload)
    except (TypeError, ValueError):
        return None


def _current_action() -> Action | None:
    payload = st.session_state.get("action_payload")
    if not isinstance(payload, dict):
        return None
    try:
        return validate_action(payload)
    except Exception:
        return None


def main() -> None:
    st.set_page_config(page_title="ActionGate | AI Action Authorization", page_icon="🛡️", layout="wide")
    _ensure_database()
    if "page" not in st.session_state:
        st.session_state.page = "Task Gateway"

    st.markdown("""
    <style>
    .stApp{background:#0b0f15}.block-container{max-width:1500px;padding-top:1.5rem}
    [data-testid="stSidebar"]{background:#101722;border-right:1px solid #273445}
    .ag-eyebrow{font-size:.72rem;letter-spacing:.16em;color:#82a7d0;font-weight:800}
    .ag-title{font-size:2.25rem;font-weight:800;letter-spacing:-.04em;color:#f4f7fb;margin:.25rem 0}
    .ag-subtitle{color:#9aabba;margin-bottom:1.1rem}
    div[data-testid="stMetric"]{background:#111a25;border:1px solid #2a394b;border-radius:12px;padding:.9rem}
    div.stButton>button{border-radius:9px;font-weight:650;min-height:2.5rem}
    </style>""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown('<div class="ag-eyebrow">SECURITY PLATFORM</div><div style="font-size:1.55rem;font-weight:800;color:#f4f7fb">🛡️ ActionGate</div><p style="color:#9aabba">AI-agent authorization gateway</p>', unsafe_allow_html=True)
        st.divider()
        page = st.radio("WORKSPACE", ["Command Center", "Task Gateway", "Approval Workflow", "Audit & Security Lab"], key="navigation")
        st.divider()
        st.caption("ENVIRONMENT")
        st.markdown("**LOCAL DEMO**")
        ai_ready = bool(os.getenv("GEMINI_API_KEY", "").strip())
        st.caption("Gemini interpreter: configured" if ai_ready else "Gemini interpreter: unavailable → local fallback")
        st.caption("Fictional SQLite data · Side effects require preview and approval")
        st.caption(f"File workspace: {workspace_root()}")

    st.markdown('<div class="ag-eyebrow">AI ACTION AUTHORIZATION GATEWAY</div><div class="ag-title">ActionGate</div><div class="ag-subtitle">Interpret the task. Inspect impact. Apply deterministic policy. Approve and revalidate before execution.</div>', unsafe_allow_html=True)
    verification, events = _load_audit()
    counts = _event_summary(events)

    if page == "Command Center":
        st.subheader("Security overview")
        cols = st.columns(4)
        cols[0].metric("Allowed", counts["ALLOW"])
        cols[1].metric("On hold", counts["HOLD"])
        cols[2].metric("Blocked", counts["BLOCK"])
        cols[3].metric("Audit chain", "VALID" if verification.valid else "INVALID")
        st.caption("Decision totals count recorded decisions and blocked task interpretations, not all possible requests.")
        left, right = st.columns([1.35, 1])
        with left:
            st.subheader("Recent authorization events")
            _render_events(events)
        with right:
            st.subheader("What ActionGate enforces")
            st.markdown("""
            - Unknown agents and unsupported operations fail closed.
            - The action must pass strict schema and permission checks.
            - Impact is calculated from the local database.
            - Updates require a separate reviewer.
            - Execution revalidates action and impact.
            - Decision source and outcome are written to the audit chain.
            """)
            st.info("Reviewer identities are demo strings, not authenticated accounts. This is not a production authorization system.")

    elif page == "Task Gateway":
        st.subheader("Give the agent a task")
        st.write("Use natural language. The interpreter can only propose actions in the strict allowlist; ActionGate's deterministic policy makes the final authorization decision.")
        task = st.text_area(
            "Task", key="task_input", height=105,
            placeholder="Examples:\n• Show standard customers\n• List pending orders\n• Mark pending orders for review\n• List files\n• Delete file demo_delete_me.txt\n• Send an email to name@example.com with subject Hello and body ...",
        )
        force_fallback = st.toggle("Force AI unavailable (demonstrate safe fallback)", value=False, help="Useful to demonstrate safe fallback even if GEMINI_API_KEY is configured.")
        if st.button("Interpret and inspect task", type="primary", use_container_width=True):
            request_id = f"req-{uuid.uuid4().hex[:12]}"
            st.session_state.request_id = request_id
            st.session_state.approval_id = None
            st.session_state.approval_request_id = None
            st.session_state.completed_request_id = None
            st.session_state.action_payload = None
            st.session_state.external_tool_plan = None
            st.session_state.external_mode = should_route_external_task(task)

            if st.session_state.external_mode:
                result = interpret_tool_task(task, request_id=request_id, requester="demo_requester", force_fallback=force_fallback)
                st.session_state.interpreter_source = result.source
                st.session_state.interpreter_status = result.status
                st.session_state.interpreter_message = result.message
                st.session_state.task_digest = result.task_digest
                st.session_state.external_tool_plan = result.plan.to_payload() if result.plan else None
                _audit_task_request(task, request_id, result.source, result.status, result.message)
                if result.plan is None:
                    st.session_state.policy_outcome = "BLOCK"
                    st.session_state.policy_reason = result.message
                    _append("task_blocked", {"request_id": request_id, "outcome": "BLOCK", "decision_source": result.source, "reason": result.message, "task_digest": result.task_digest})
                else:
                    inspection = inspect_tool_plan(result.plan)
                    outcome, reason = decision_for_tool(result.plan, inspection)
                    st.session_state.policy_outcome = outcome
                    st.session_state.policy_reason = reason if inspection.reliable else (inspection.reason or reason)
                    _append("decision_recorded", {"request_id": request_id, "tool": result.plan.tool, "action_digest": hashlib.sha256(json.dumps(result.plan.to_payload(), sort_keys=True).encode()).hexdigest(), "impact_digest": inspection.digest, "impact_row_count": inspection.row_count, "outcome": outcome, "reason": st.session_state.policy_reason, "decision_source": result.source})
            else:
                result = interpret_task(task, request_id=request_id, requested_by="demo_requester", force_fallback=force_fallback)
                st.session_state.interpreter_source = result.source
                st.session_state.interpreter_status = result.status
                st.session_state.interpreter_message = result.message
                st.session_state.task_digest = result.task_digest
                st.session_state.action_payload = result.action.to_payload() if result.action else None
                if result.action is None:
                    _audit_task_request(task, request_id, result.source, result.status, result.message)
                    _append("task_blocked", {"request_id": request_id, "outcome": "BLOCK", "decision_source": result.source, "reason": result.message, "task_digest": result.task_digest})
                    st.session_state.policy_outcome = "BLOCK"
                    st.session_state.policy_reason = result.message
                else:
                    impact = inspect_impact(DATABASE_PATH, result.action)
                    decision = decide(result.action, impact)
                    st.session_state.policy_outcome = decision.outcome
                    st.session_state.policy_reason = decision.reason
                    _audit_task_request(task, request_id, result.source, result.status, result.message)
                    _audit_decision(result.action, result.source, decision.outcome, decision.reason, impact.digest, impact.row_count)

        action = _current_action()
        if st.session_state.get("request_id") and "policy_outcome" in st.session_state:
            st.divider()
            st.subheader("Interpretation and authorization")
            p1, p2, p3 = st.columns(3)
            p1.metric("Request ID", st.session_state.request_id)
            p2.metric("Interpreter path", st.session_state.interpreter_source)
            p3.metric("Status", st.session_state.interpreter_status)
            st.caption(st.session_state.interpreter_message)
            outcome = st.session_state.policy_outcome
            reason = st.session_state.policy_reason
            _decision_banner(outcome, reason)

            if st.session_state.get("external_mode"):
                plan = _current_tool_plan()
                if plan is None:
                    st.error(reason)
                else:
                    inspection = inspect_tool_plan(plan)
                    current_outcome, current_reason = decision_for_tool(plan, inspection)
                    if not inspection.reliable:
                        st.error(inspection.reason or current_reason)
                    st.markdown("#### Proposed tool action")
                    st.write({"tool": plan.tool, "request_id": plan.request_id, "requester": plan.requester, "explanation": plan.explanation})
                    if plan.tool == "delete_file":
                        st.warning("File deletion is scoped to the configured workspace and uses a recoverable quarantine, not permanent erasure.")
                        st.write({"workspace": str(workspace_root()), **inspection.details})
                    elif plan.tool == "send_email":
                        st.markdown("##### Email preview")
                        st.write({"To": plan.recipient, "Subject": plan.subject, "SMTP configured": inspection.details.get("smtp_configured", False)})
                        st.text_area("Email body preview", value=plan.body, height=150, disabled=True, key=f"email_preview_{plan.request_id}")
                        st.caption("No email is sent at interpretation time. Sending requires configured SMTP plus approval and explicit confirmation.")
                    elif plan.tool == "list_files":
                        st.write({"workspace": str(workspace_root()), **inspection.details})

                    st.markdown("#### Verified impact")
                    st.metric("Items affected / listed", inspection.row_count)
                    st.caption("Plan/impact digest")
                    st.code(inspection.digest or "unavailable")
                    _decision_banner(current_outcome, current_reason)

                    if current_outcome == "ALLOW" and plan.tool == "list_files":
                        if st.button("Execute read-only file listing", type="primary", key="run_list_files"):
                            result = execute_tool_plan(DATABASE_PATH, plan, inspection)
                            if result.success:
                                st.success(result.message)
                                st.write(result.details)
                                st.session_state.completed_request_id = plan.request_id
                            else:
                                st.error(result.message)
                    elif current_outcome == "HOLD":
                        reviewer = st.text_input("Separate reviewer identity", value="demo_reviewer", key=f"tool_reviewer_{plan.request_id}")
                        if st.button("Create 5-minute tool approval", key=f"tool_approve_{plan.request_id}"):
                            try:
                                approval_id = create_tool_approval(DATABASE_PATH, plan, inspection, reviewer)
                                st.session_state.approval_id = approval_id
                                st.session_state.approval_request_id = plan.request_id
                                st.success("One-time approval created for this exact tool plan and impact.")
                            except Exception as err:
                                st.error(str(err))
                        approval_id = st.session_state.get("approval_id") if st.session_state.get("approval_request_id") == plan.request_id else None
                        confirmed = st.checkbox("I reviewed the preview and confirm this exact side effect.", key=f"tool_confirm_{plan.request_id}")
                        if approval_id:
                            st.caption("Approval ID")
                            st.code(approval_id)
                            if st.button("Execute approved tool action", type="primary", key=f"tool_execute_{plan.request_id}", disabled=not confirmed):
                                result = execute_tool_plan(DATABASE_PATH, plan, inspection, approval_id=approval_id, explicitly_confirmed=confirmed)
                                if result.success:
                                    st.success(result.message)
                                    st.json(result.details)
                                    st.session_state.completed_request_id = plan.request_id
                                    st.session_state.approval_id = None
                                    st.session_state.approval_request_id = None
                                else:
                                    st.error(result.message)
                    elif current_outcome == "BLOCK":
                        st.error("No execution control is available because this task was blocked.")

            elif action is not None:
                impact = inspect_impact(DATABASE_PATH, action)
                a, b = st.columns([1, 1])
                with a:
                    st.markdown("#### Structured action (validated)")
                    st.json(action.to_payload())
                with b:
                    st.markdown("#### Database-derived impact")
                    st.metric("Affected records", impact.row_count)
                    st.write("Primary keys", impact.primary_keys)
                    st.caption("Impact SHA-256 digest")
                    st.code(impact.digest or "unavailable")

                if st.session_state.get("completed_request_id") == action.request_id:
                    st.success("This request has already executed. Submit a new task to initiate another action.")
                elif outcome == "ALLOW" and action.operation == "SELECT":
                    if st.button("Execute authorized read", type="primary", key="execute_read"):
                        result = execute_action(DATABASE_PATH, action)
                        if result.success:
                            st.session_state.completed_request_id = action.request_id
                            st.success("Read executed successfully.")
                            if result.rows:
                                st.dataframe(result.rows, use_container_width=True, hide_index=True)
                        else:
                            st.error(result.reason)
                        _append("task_execution_result", {"request_id": action.request_id, "success": result.success, "decision_source": st.session_state.interpreter_source, "reason": result.reason})

                elif outcome == "HOLD" and action.operation == "UPDATE":
                    st.warning("Mutation held. A separate reviewer must approve this exact action and impact before execution.")
                    reviewer = st.text_input("Reviewer identity", value="demo_reviewer", key="reviewer_input")
                    if st.button("Create 5-minute approval", key="create_approval"):
                        try:
                            approval = create_approval(DATABASE_PATH, action, impact, reviewer, datetime.now(UTC) + timedelta(minutes=5))
                            st.session_state.approval_id = approval.approval_id
                            st.session_state.approval_request_id = action.request_id
                            st.success("Approval created and bound to this action and impact.")
                            st.code(approval.approval_id)
                        except ApprovalError as error:
                            st.error(str(error))
                    approval_id = st.session_state.get("approval_id") if st.session_state.get("approval_request_id") == action.request_id else None
                    if approval_id:
                        st.info("Execution will recompute impact and consume the approval atomically with the update.")
                        if st.button("Execute approved update", type="primary", key="execute_update"):
                            result = execute_action(DATABASE_PATH, action, approval_id)
                            if result.success:
                                st.session_state.completed_request_id = action.request_id
                                st.success(f"Update executed. Affected keys: {result.affected_primary_keys}")
                                st.session_state.approval_id = None
                                st.session_state.approval_request_id = None
                            else:
                                st.error(result.reason)
                            _append("task_execution_result", {"request_id": action.request_id, "success": result.success, "decision_source": st.session_state.interpreter_source, "reason": result.reason})
                else:
                    st.error("No execution control is offered for a blocked or unsupported action.")

    elif page == "Approval Workflow":
        st.subheader("Approval workflow")
        action = _current_action()
        if action is None or st.session_state.get("policy_outcome") != "HOLD":
            st.info("No held action is waiting in this browser session. Submit a mutation from Task Gateway first.")
        else:
            if st.session_state.get("completed_request_id") == action.request_id:
                st.success("This request has already executed; submit a new task to create another request.")
                st.stop()
            st.write({"request_id": action.request_id, "operation": action.operation, "table": action.table, "requester": action.requested_by})
            impact = inspect_impact(DATABASE_PATH, action)
            st.metric("Current affected rows", impact.row_count)
            st.write("Current primary keys", impact.primary_keys)
            st.caption("Approvals are valid only for the exact action digest and current impact digest.")
            approval_id = st.session_state.get("approval_id") if st.session_state.get("approval_request_id") == action.request_id else None
            if approval_id:
                st.success("Approval exists for this request.")
                st.code(approval_id)
                if st.button("Execute approved action", type="primary"):
                    result = execute_action(DATABASE_PATH, action, approval_id)
                    if result.success:
                        st.session_state.completed_request_id = action.request_id
                        st.success(result.reason)
                        st.session_state.approval_id = None
                        st.session_state.approval_request_id = None
                    else:
                        st.error(result.reason)
            else:
                st.warning("No active approval for the current request. Create it in Task Gateway.")

    elif page == "Audit & Security Lab":
        st.subheader("Audit integrity")
        verification, events = _load_audit()
        a, b, c = st.columns(3)
        a.metric("Chain", "VALID" if verification.valid else "INVALID")
        b.metric("Events", verification.event_count)
        c.metric("Recent events displayed", min(len(events), 100))
        st.success("Hash-chain verification passed." if verification.valid else verification.reason)
        _render_events(events)
        st.caption("A hash chain detects many edits/reorders, but cannot prevent a privileged user truncating the local database.")
        st.divider()
        st.subheader("Automated security tests")
        st.write("Run in the project terminal; the tests use temporary databases for tampering and rollback scenarios.")
        st.code('& "D:\\ACTIONGATE\\actiongate\\.venv\\Scripts\\python.exe" -m pytest -q', language="powershell")
        st.markdown("""
        **Demonstration scenarios:** unsupported task fails closed; prompt-injection-like bypass request is blocked; schema allowlists reject unknown operations; mutations require reviewer approval; altered actions/replay/impact drift are rejected; AI outage can be forced to demonstrate the restricted local fallback; decision provenance is audited.
        """)


if __name__ == "__main__":
    main()
