from __future__ import annotations

import pytest

from app.schema import SchemaValidationError, validate_action


def valid_action() -> dict[str, object]:
    return {
        "request_id": "req-1",
        "agent_id": "support_agent",
        "operation": "SELECT",
        "table": "customers",
        "columns": ["customer_id", "name"],
        "filters": [{"column": "tier", "operator": "eq", "value": "standard"}],
        "requested_by": "demo_user",
    }


def test_valid_action_is_normalized() -> None:
    action = validate_action(valid_action())
    assert action.columns == ("customer_id", "name")
    assert action.filters[0].operator == "eq"


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "no"},
        {"agent_id": "unknown_agent"},
        {"table": "customers; DROP TABLE customers"},
        {"columns": ["*" ]},
        {"filters": [{"column": "tier", "operator": "LIKE", "value": "%"}]},
        {"filters": "tier = 'standard'"},
    ],
)
def test_malformed_or_unsafe_actions_are_rejected(change: dict[str, object]) -> None:
    payload = valid_action()
    payload.update(change)
    with pytest.raises(SchemaValidationError):
        validate_action(payload)


def test_update_requires_allowed_set_values() -> None:
    payload = {
        "request_id": "req-2",
        "agent_id": "operations_agent",
        "operation": "UPDATE",
        "table": "orders",
        "columns": ["order_id", "status"],
        "filters": [{"column": "status", "operator": "eq", "value": "pending"}],
        "set_values": {"status": "review"},
        "requested_by": "demo_user",
    }
    assert validate_action(payload).operation == "UPDATE"
