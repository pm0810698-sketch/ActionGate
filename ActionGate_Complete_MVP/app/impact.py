"""Database-authoritative, non-mutating impact inspection."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .database import connect_read_only, primary_key_for, where_clause
from .schema import Action, TABLES, validate_action


@dataclass(frozen=True)
class Impact:
    primary_keys: tuple[int, ...]
    row_count: int
    digest: str
    reliable: bool
    reason: str = ""


def inspect_impact(database_path: str | Path, action: Action) -> Impact:
    """Select affected primary keys only; query-only mode prevents data mutation."""
    try:
        with connect_read_only(database_path) as connection:
            return inspect_impact_connection(connection, action)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        return Impact((), 0, "", False, f"impact inspection failed: {error}")


def inspect_impact_connection(connection: sqlite3.Connection, action: Action) -> Impact:
    """Inspect impact using an existing transaction without changing any rows."""
    action = validate_action(action.to_payload())
    primary_key = primary_key_for(action.table)
    where_sql, parameters = where_clause(action.filters)
    # Both identifiers are selected solely from schema TABLES after revalidation.
    query = f"SELECT {primary_key} FROM {action.table}{where_sql} ORDER BY {primary_key}"
    primary_keys = tuple(int(row[0]) for row in connection.execute(query, parameters))
    return _reliable_impact(primary_keys)


def _reliable_impact(primary_keys: tuple[int, ...]) -> Impact:
    sorted_keys = tuple(sorted(primary_keys))
    return Impact(sorted_keys, len(sorted_keys), primary_key_digest(sorted_keys), True)


def primary_key_digest(primary_keys: tuple[int, ...]) -> str:
    """Return the stable SHA-256 digest for an already sorted key sequence."""
    encoded = json.dumps(primary_keys, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
