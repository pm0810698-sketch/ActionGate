from __future__ import annotations

import sqlite3

from app.database import initialize_demo_database
from app.impact import inspect_impact
from app.schema import validate_action


def action_for(filters: list[dict[str, object]]):
    return validate_action(
        {
            "request_id": "impact-1",
            "agent_id": "support_agent",
            "operation": "SELECT",
            "table": "customers",
            "columns": ["customer_id", "name"],
            "filters": filters,
            "requested_by": "demo_user",
        }
    )


def test_impact_has_sorted_keys_count_and_stable_digest(tmp_path) -> None:
    database = tmp_path / "demo.db"
    assert initialize_demo_database(database)
    impact = inspect_impact(database, action_for([{"column": "tier", "operator": "eq", "value": "standard"}]))
    assert impact.primary_keys == (1, 3)
    assert impact.row_count == 2
    assert impact.reliable
    assert impact.digest == inspect_impact(database, action_for([{"column": "tier", "operator": "eq", "value": "standard"}])).digest


def test_empty_impact_is_reliable(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    impact = inspect_impact(database, action_for([{"column": "tier", "operator": "eq", "value": "absent"}]))
    assert impact.primary_keys == ()
    assert impact.row_count == 0
    assert impact.reliable


def test_inspection_does_not_modify_database(tmp_path) -> None:
    database = tmp_path / "demo.db"
    initialize_demo_database(database)
    with sqlite3.connect(database) as connection:
        before = connection.execute("SELECT status FROM orders WHERE order_id = 101").fetchone()
    inspect_impact(database, action_for([]))
    with sqlite3.connect(database) as connection:
        after = connection.execute("SELECT status FROM orders WHERE order_id = 101").fetchone()
    assert before == after


def test_inspection_does_not_create_a_missing_database(tmp_path) -> None:
    database = tmp_path / "missing.db"
    impact = inspect_impact(database, action_for([]))
    assert not impact.reliable
    assert not database.exists()


def test_initialization_does_not_overwrite_existing_database(tmp_path) -> None:
    database = tmp_path / "demo.db"
    assert initialize_demo_database(database)
    assert not initialize_demo_database(database)
