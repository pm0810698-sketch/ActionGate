"""Example agent client. It has no database/file/email tool access of its own.

Every task is sent to the ActionGate HTTP gateway for policy enforcement.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.gateway_client import ActionGateClient, GatewayClientError  # noqa: E402


def show_preview(result: dict[str, object]) -> None:
    print("\n--- ACTIONGATE AUTHORIZATION RESULT ---")
    print("request_id:", result.get("request_id"))
    interpretation = result.get("interpretation") or {}
    decision = result.get("decision") or {}
    impact = result.get("impact") or {}
    print("interpreter:", interpretation.get("source", "unknown"))
    print("decision:", decision.get("outcome", "BLOCK"))
    print("reason:", decision.get("reason", "No decision reason"))
    print("impact count:", impact.get("row_count", 0))
    print("impact details:")
    print(json.dumps(impact.get("details", {}), indent=2, ensure_ascii=False))
    print("proposed action:")
    print(json.dumps(result.get("proposal"), indent=2, ensure_ascii=False))
    print("---------------------------------------\n")


def main() -> int:
    client = ActionGateClient(os.getenv("ACTIONGATE_GATEWAY_URL", "http://127.0.0.1:8765"))
    try:
        health = client.health()
        print("Connected to", health.get("service"), "audit chain:", health.get("audit_chain_valid"))
    except GatewayClientError as error:
        print(error)
        print("Start the gateway in another terminal with: python -m app.gateway_api")
        return 2

    print("ActionGate demo agent — all tool requests go through the gateway.")
    print("Try: Show standard customers | List pending orders | Mark pending orders for review | List files | Delete file demo_delete_me.txt")
    print("Type 'quit' to exit. This agent has no direct tool execution functions.\n")

    while True:
        try:
            task = input("Task for agent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if task.lower() in {"quit", "exit"}:
            return 0
        if not task:
            continue
        inspected = client.inspect_task(task)
        if not inspected.get("ok"):
            print("Gateway rejected request:", inspected.get("error", inspected))
            continue
        show_preview(inspected)
        outcome = (inspected.get("decision") or {}).get("outcome")
        request_id = str(inspected.get("request_id", ""))
        if outcome == "BLOCK":
            print("Blocked. No execution was offered.\n")
            continue
        if outcome == "ALLOW":
            answer = input("Execute this authorized action? Type YES to continue: ").strip()
            if answer != "YES":
                print("Cancelled. Nothing executed.\n")
                continue
            result = client.execute(request_id, confirmed=True)
            print(json.dumps(result, indent=2, ensure_ascii=False), "\n")
            continue
        if outcome == "HOLD":
            reviewer = input("Reviewer identity (demo only)> ").strip()
            if not reviewer:
                print("Approval cancelled. Nothing executed.\n")
                continue
            approval = client.approve(request_id, reviewer)
            if not approval.get("ok"):
                print("Approval failed:", approval.get("error", approval), "\n")
                continue
            print("Approval issued:", approval.get("approval_id"))
            answer = input("Execute the exact approved action? Type YES to continue: ").strip()
            if answer != "YES":
                print("Execution cancelled. Approval remains unexecuted and will expire.\n")
                continue
            result = client.execute(request_id, approval_id=str(approval.get("approval_id")), confirmed=True)
            print(json.dumps(result, indent=2, ensure_ascii=False), "\n")


if __name__ == "__main__":
    raise SystemExit(main())
