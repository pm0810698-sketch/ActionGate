from __future__ import annotations

from app.impact import Impact, primary_key_digest
from app.policy import decide
from app.schema import Action, validate_action


def read_action() -> Action:
    return validate_action(
        {
            "request_id": "policy-1",
            "agent_id": "support_agent",
            "operation": "SELECT",
            "table": "customers",
            "columns": ["customer_id"],
            "filters": [],
            "requested_by": "demo_user",
        }
    )


def reliable_impact() -> Impact:
    return Impact((1,), 1, primary_key_digest((1,)), True)


def test_policy_allows_authorized_read() -> None:
    assert decide(read_action(), reliable_impact()).outcome == "ALLOW"


def test_policy_holds_supported_mutation() -> None:
    action = validate_action(
        {
            "request_id": "policy-2",
            "agent_id": "operations_agent",
            "operation": "UPDATE",
            "table": "orders",
            "columns": ["order_id", "status"],
            "filters": [{"column": "order_id", "operator": "eq", "value": 101}],
            "set_values": {"status": "review"},
            "requested_by": "demo_user",
        }
    )
    assert decide(action, reliable_impact()).outcome == "HOLD"


def test_policy_blocks_missing_or_unreliable_impact() -> None:
    assert decide(read_action(), None).outcome == "BLOCK"
    assert decide(read_action(), Impact((), 0, "", False)).outcome == "BLOCK"


def test_policy_blocks_unknown_or_malformed_action() -> None:
    unknown = Action("x", "unknown", "SELECT", "customers", ("customer_id",), (), "demo")
    assert decide(unknown, reliable_impact()).outcome == "BLOCK"
    assert decide({"operation": "SELECT"}, reliable_impact()).outcome == "BLOCK"


def test_policy_blocks_declared_impact_limit_breach() -> None:
    payload = read_action().to_payload()
    payload["declared_impact_limit"] = 0
    assert decide(validate_action(payload), reliable_impact()).outcome == "BLOCK"
