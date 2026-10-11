"""Deterministic, fail-closed Phase 1 policy decisions."""

from __future__ import annotations

from dataclasses import dataclass

from .impact import Impact, primary_key_digest
from .schema import Action, SchemaValidationError, validate_action

# Server-side controls; never read these from the agent's request.
MAX_UPDATE_ROWS = 10
# In this fictional demo, order status is the only explicitly reversible
# mutation surface. Payments, messages, deletes, and other external effects
# are not representable in the allowlisted action schema.
REVERSIBLE_UPDATE_TARGETS = {"orders": {"status": frozenset({"pending", "review"})}}


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str


def decide(action: object, impact: Impact | None) -> Decision:
    """Return ALLOW, HOLD, or BLOCK using deterministic rules only."""
    try:
        if not isinstance(action, Action):
            raise SchemaValidationError("action is not validated")
        action = validate_action(action.to_payload())
    except (SchemaValidationError, TypeError, AttributeError) as error:
        return Decision("BLOCK", f"invalid action: {error}")

    if impact is None or not isinstance(impact, Impact) or not impact.reliable:
        return Decision("BLOCK", "reliable database impact is required")
    if (
        impact.row_count != len(impact.primary_keys)
        or impact.row_count < 0
        or tuple(sorted(impact.primary_keys)) != impact.primary_keys
        or impact.digest != primary_key_digest(impact.primary_keys)
    ):
        return Decision("BLOCK", "impact is inconsistent")
    if action.declared_impact_limit is not None and impact.row_count > action.declared_impact_limit:
        return Decision("BLOCK", "affected rows exceed declared impact limit")

    if action.operation == "SELECT":
        return Decision("ALLOW", "authorized read with reliable database impact")
    if action.operation == "UPDATE":
        if not action.filters:
            return Decision("BLOCK", "UPDATE requires at least one filter")
        reversible_targets = REVERSIBLE_UPDATE_TARGETS.get(action.table, {})
        if not action.set_values or any(
            column not in reversible_targets or value not in reversible_targets[column]
            for column, value in action.set_values
        ):
            return Decision("BLOCK", "mutation is outside the reversible-operation allowlist")
        if impact.row_count > MAX_UPDATE_ROWS:
            return Decision("BLOCK", f"affected rows exceed server limit of {MAX_UPDATE_ROWS}")
        return Decision("HOLD", "reversible mutation requires separate approval")
    return Decision("BLOCK", "unsupported action")
