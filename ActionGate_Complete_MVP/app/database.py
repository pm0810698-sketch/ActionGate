"""SQLite demo database creation and safe query helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

from .schema import Filter, TABLES


_DEMO_CUSTOMERS = (
    (1, "Avery North", "avery.north@example.test", "standard"),
    (2, "Blake River", "blake.river@example.test", "premium"),
    (3, "Casey Vale", "casey.vale@example.test", "standard"),
)
_DEMO_ORDERS = (
    (101, 1, "pending", 2400),
    (102, 2, "paid", 5100),
    (103, 1, "shipped", 1750),
)


def initialize_demo_database(path: str | Path) -> bool:
    """Create fictional seed data once; return False without touching an existing DB."""
    database_path = Path(path)
    if database_path.exists():
        return False
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                tier TEXT NOT NULL
            );
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                total_cents INTEGER NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO customers (customer_id, name, email, tier) VALUES (?, ?, ?, ?)",
            _DEMO_CUSTOMERS,
        )
        connection.executemany(
            "INSERT INTO orders (order_id, customer_id, status, total_cents) VALUES (?, ?, ?, ?)",
            _DEMO_ORDERS,
        )
    return True


def connect_read_only(path: str | Path) -> sqlite3.Connection:
    """Open an existing database with SQLite's query-only protection enabled."""
    database_uri = Path(path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def primary_key_for(table: str) -> str:
    return str(TABLES[table]["primary_key"])


def where_clause(filters: Sequence[Filter]) -> tuple[str, tuple[object, ...]]:
    """Build a parameterized predicate from already validated filter objects."""
    parts: list[str] = []
    parameters: list[object] = []
    operators = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
    for item in filters:
        if item.operator == "in":
            values = item.value
            assert isinstance(values, list)  # Guaranteed by schema validation.
            parts.append(f"{item.column} IN ({', '.join('?' for _ in values)})")
            parameters.extend(values)
        else:
            parts.append(f"{item.column} {operators[item.operator]} ?")
            parameters.append(item.value)
    return (" WHERE " + " AND ".join(parts) if parts else "", tuple(parameters))
