"""Strict, allowlisted structured actions for the local demo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping


class SchemaValidationError(ValueError):
    """Raised when untrusted action data is not a supported action."""


FILTER_OPERATORS: Final[frozenset[str]] = frozenset(
    {"eq", "ne", "lt", "lte", "gt", "gte", "in"}
)

TABLES: Final[dict[str, dict[str, Any]]] = {
    "customers": {
        "primary_key": "customer_id",
        "columns": frozenset({"customer_id", "name", "email", "tier"}),
        "numeric_columns": frozenset({"customer_id"}),
        "writable_columns": frozenset({"tier"}),
    },
    "orders": {
        "primary_key": "order_id",
        "columns": frozenset({"order_id", "customer_id", "status", "total_cents"}),
        "numeric_columns": frozenset({"order_id", "customer_id", "total_cents"}),
        "writable_columns": frozenset({"status"}),
    },
}

# These identities are deliberately small and fictional. They are demo allowlists,
# not an authentication mechanism.
AGENT_PERMISSIONS: Final[dict[str, frozenset[tuple[str, str]]]] = {
    "support_agent": frozenset({("SELECT", "customers"), ("SELECT", "orders")}),
    "operations_agent": frozenset({("SELECT", "orders"), ("UPDATE", "orders")}),
}

_ACTION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "request_id",
        "agent_id",
        "operation",
        "table",
        "columns",
        "filters",
        "requested_by",
        "declared_impact_limit",
        "set_values",
    }
)


@dataclass(frozen=True)
class Filter:
    column: str
    operator: str
    value: object


@dataclass(frozen=True)
class Action:
    request_id: str
    agent_id: str
    operation: str
    table: str
    columns: tuple[str, ...]
    filters: tuple[Filter, ...]
    requested_by: str
    declared_impact_limit: int | None = None
    set_values: tuple[tuple[str, object], ...] = ()

    def to_payload(self) -> dict[str, object]:
        """Return a canonical payload suitable for revalidation."""
        payload: dict[str, object] = {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "operation": self.operation,
            "table": self.table,
            "columns": list(self.columns),
            "filters": [
                {"column": item.column, "operator": item.operator, "value": item.value}
                for item in self.filters
            ],
            "requested_by": self.requested_by,
        }
        if self.declared_impact_limit is not None:
            payload["declared_impact_limit"] = self.declared_impact_limit
        if self.set_values:
            payload["set_values"] = dict(self.set_values)
        return payload


def validate_action(payload: Mapping[str, object]) -> Action:
    """Validate untrusted structured data without accepting SQL syntax."""
    if not isinstance(payload, Mapping):
        raise SchemaValidationError("action must be an object")
    unknown = set(payload) - _ACTION_FIELDS
    if unknown:
        raise SchemaValidationError(f"unknown action fields: {sorted(unknown)}")

    request_id = _required_text(payload, "request_id")
    agent_id = _required_text(payload, "agent_id")
    operation = _required_text(payload, "operation")
    table = _required_text(payload, "table")
    requested_by = _required_text(payload, "requested_by").strip()
    if operation not in {"SELECT", "UPDATE"}:
        raise SchemaValidationError("unsupported operation")
    if table not in TABLES:
        raise SchemaValidationError("unsupported table")
    if agent_id not in AGENT_PERMISSIONS:
        raise SchemaValidationError("unknown agent")
    if (operation, table) not in AGENT_PERMISSIONS[agent_id]:
        raise SchemaValidationError("agent is not authorized for this action")

    columns = _columns(payload.get("columns"), table)
    filters = _filters(payload.get("filters"), table)
    impact_limit = _impact_limit(payload.get("declared_impact_limit"))
    set_values = _set_values(payload.get("set_values"), table, operation)
    return Action(
        request_id=request_id,
        agent_id=agent_id,
        operation=operation,
        table=table,
        columns=columns,
        filters=filters,
        requested_by=requested_by,
        declared_impact_limit=impact_limit,
        set_values=set_values,
    )


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise SchemaValidationError(f"{field} must be a non-empty string up to 128 characters")
    return value


def _columns(value: object, table: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise SchemaValidationError("columns must be a non-empty list")
    if not all(isinstance(column, str) for column in value):
        raise SchemaValidationError("columns must contain strings")
    if len(set(value)) != len(value) or not set(value).issubset(TABLES[table]["columns"]):
        raise SchemaValidationError("unsupported or duplicate column")
    return tuple(value)


def _filters(value: object, table: str) -> tuple[Filter, ...]:
    if not isinstance(value, list):
        raise SchemaValidationError("filters must be a list")
    result: list[Filter] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"column", "operator", "value"}:
            raise SchemaValidationError("each filter must contain only column, operator, and value")
        column, operator, raw_value = item["column"], item["operator"], item["value"]
        if not isinstance(column, str) or column not in TABLES[table]["columns"]:
            raise SchemaValidationError("unsupported filter column")
        if not isinstance(operator, str) or operator not in FILTER_OPERATORS:
            raise SchemaValidationError("unsupported filter operator")
        if operator in {"lt", "lte", "gt", "gte"} and column not in TABLES[table]["numeric_columns"]:
            raise SchemaValidationError("comparison operator requires a numeric column")
        _validate_filter_value(column, operator, raw_value, table)
        result.append(Filter(column, operator, raw_value))
    return tuple(result)


def _validate_filter_value(column: str, operator: str, value: object, table: str) -> None:
    values = value if operator == "in" else [value]
    if operator == "in" and (not isinstance(value, list) or not 1 <= len(value) <= 50):
        raise SchemaValidationError("in values must be a list containing 1 to 50 items")
    numeric = column in TABLES[table]["numeric_columns"]
    for item in values:
        expected = isinstance(item, int) and not isinstance(item, bool) if numeric else isinstance(item, str)
        if not expected:
            raise SchemaValidationError("filter value has the wrong type")
        if isinstance(item, str) and (not item or len(item) > 256):
            raise SchemaValidationError("string filter value must be non-empty and at most 256 characters")


def _impact_limit(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SchemaValidationError("declared_impact_limit must be a non-negative integer")
    return value


def _set_values(value: object, table: str, operation: str) -> tuple[tuple[str, object], ...]:
    if operation == "SELECT":
        if value is not None:
            raise SchemaValidationError("SELECT actions cannot include set_values")
        return ()
    if not isinstance(value, Mapping) or not value:
        raise SchemaValidationError("UPDATE actions require non-empty set_values")
    if not set(value).issubset(TABLES[table]["writable_columns"]):
        raise SchemaValidationError("unsupported writable column")
    if not all(isinstance(item, str) and item and len(item) <= 256 for item in value.values()):
        raise SchemaValidationError("set_values must contain non-empty string values")
    return tuple(sorted(value.items()))
