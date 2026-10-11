from __future__ import annotations

import sqlite3

from app.gateway_service import GatewayService


def test_read_task_returns_allow_and_can_execute(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(tmp_path / "workspace"))
    service = GatewayService(tmp_path / "demo.db")

    inspected = service.inspect_task({"task": "Show standard customers"})

    assert inspected["ok"] is True
    assert inspected["kind"] == "database"
    assert inspected["decision"]["outcome"] == "ALLOW"
    assert inspected["impact"]["row_count"] == 2
    assert inspected["interpretation"]["source"] == "deterministic_fallback"

    executed = service.execute({"request_id": inspected["request_id"], "confirmed": True})
    assert executed["ok"] is True
    assert len(executed["rows"]) == 2


def test_mutation_requires_approval_then_revalidates_and_executes(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(tmp_path / "workspace"))
    db = tmp_path / "demo.db"
    service = GatewayService(db)

    inspected = service.inspect_task({"task": "Mark pending orders for review"})
    assert inspected["decision"]["outcome"] == "HOLD"

    without_approval = service.execute({"request_id": inspected["request_id"], "confirmed": True})
    assert without_approval["ok"] is False
    assert "approval" in without_approval["error"].lower()

    approval = service.approve({"request_id": inspected["request_id"], "reviewer": "reviewer-1"})
    assert approval["ok"] is True

    executed = service.execute({
        "request_id": inspected["request_id"],
        "approval_id": approval["approval_id"],
        "confirmed": True,
    })
    assert executed["ok"] is True
    assert executed["affected_primary_keys"]
    assert executed["authorization_decision"] == "HOLD"
    assert executed["execution_status"] == "SUCCEEDED"
    assert executed["outcome"] == "SUCCEEDED"

    with sqlite3.connect(db) as conn:
        values = conn.execute("SELECT status FROM orders WHERE order_id = 101").fetchone()
    assert values[0] == "review"

    replay = service.execute({
        "request_id": inspected["request_id"],
        "approval_id": approval["approval_id"],
        "confirmed": True,
    })
    assert replay["ok"] is False
    assert "completed" in replay["error"].lower() or "replay" in replay["error"].lower()


def test_file_delete_requires_approval_and_moves_to_quarantine(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "demo_delete_me.txt"
    target.write_text("test file", encoding="utf-8")
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(workspace))
    service = GatewayService(tmp_path / "demo.db")

    inspected = service.inspect_task({"task": "Delete file demo_delete_me.txt"})
    assert inspected["kind"] == "tool"
    assert inspected["decision"]["outcome"] == "HOLD"

    denied = service.execute({"request_id": inspected["request_id"], "confirmed": True})
    assert denied["ok"] is False
    assert target.exists()

    approval = service.approve({"request_id": inspected["request_id"], "reviewer": "reviewer-1"})
    assert approval["ok"] is True
    executed = service.execute({
        "request_id": inspected["request_id"],
        "approval_id": approval["approval_id"],
        "confirmed": True,
    })
    assert executed["ok"] is True
    assert executed["authorization_decision"] == "HOLD"
    assert executed["execution_status"] == "SUCCEEDED"
    assert not target.exists()
    assert (workspace / ".actiongate_trash").exists()


def test_unknown_task_fails_closed_and_is_audited(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(tmp_path / "workspace"))
    service = GatewayService(tmp_path / "demo.db")

    result = service.inspect_task({"task": "Call Samarth and tell him to come"})
    assert result["decision"]["outcome"] == "BLOCK"
    assert result["proposal"] is None

    events = service.events()
    event_types = [item["event_type"] for item in events["events"]]
    assert "gateway_task_received" in event_types
    assert "gateway_decision" in event_types
    assert events["chain_valid"] is True
