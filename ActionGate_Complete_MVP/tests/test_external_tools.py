from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.database import initialize_demo_database
from app.external_tools import (
    ToolPlan,
    create_tool_approval,
    execute_tool_plan,
    inspect_tool_plan,
    interpret_tool_task,
    should_route_external_task,
    workspace_root,
)


def test_external_task_route_and_limited_fallback_list_files(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(tmp_path / "workspace"))
    task = "List files"
    assert should_route_external_task(task)
    result = interpret_tool_task(task, request_id="r1")
    assert result.plan is not None
    assert result.plan.tool == "list_files"
    assert result.source == "deterministic_fallback"


def test_delete_file_is_scoped_and_requires_approval_and_confirmation(monkeypatch, tmp_path):
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(root))
    target = root / "report.txt"
    target.write_text("test content", encoding="utf-8")

    plan = ToolPlan(
        request_id="delete-1",
        requester="requester",
        tool="delete_file",
        path="report.txt",
    )
    inspection = inspect_tool_plan(plan)
    assert inspection.reliable

    blocked_without_confirm = execute_tool_plan(
        database, plan, inspection, explicitly_confirmed=False
    )
    assert not blocked_without_confirm.success
    assert target.exists()

    approval = create_tool_approval(database, plan, inspection, "reviewer")
    result = execute_tool_plan(
        database,
        plan,
        inspection,
        approval_id=approval,
        explicitly_confirmed=True,
    )
    assert result.success
    assert not target.exists()
    assert (root / result.details["quarantine_path"]).exists()

    replay = execute_tool_plan(
        database,
        plan,
        inspection,
        approval_id=approval,
        explicitly_confirmed=True,
    )
    assert not replay.success


def test_delete_file_cannot_escape_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(tmp_path / "workspace"))
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    plan = ToolPlan(
        request_id="delete-outside",
        requester="requester",
        tool="delete_file",
        path="../outside.txt",
    )
    inspection = inspect_tool_plan(plan)
    assert not inspection.reliable
    assert outside.exists()


def test_email_task_without_smtp_is_blocked_and_not_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("ACTIONGATE_WORKSPACE", str(tmp_path / "workspace"))
    for key in ("ACTIONGATE_SMTP_HOST", "ACTIONGATE_SMTP_USERNAME", "ACTIONGATE_SMTP_PASSWORD", "ACTIONGATE_SMTP_FROM"):
        monkeypatch.delenv(key, raising=False)
    plan = ToolPlan(
        request_id="email-1",
        requester="requester",
        tool="send_email",
        recipient="person@example.com",
        subject="Hello",
        body="A demo email",
    )
    inspection = inspect_tool_plan(plan)
    assert not inspection.reliable
    result = execute_tool_plan(tmp_path / "nonexistent.db", plan, inspection, explicitly_confirmed=True)
    assert not result.success


def test_fallback_blocks_send_email_without_real_ai(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = interpret_tool_task(
        "Send an email to person@example.com subject Hi body Hello",
        request_id="email-fallback",
    )
    assert result.plan is None
    assert result.status == "BLOCK"
