from __future__ import annotations

import sqlite3

from app.audit import append_event, verify_chain


def test_audit_chain_detects_modification_and_reordering(tmp_path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        append_event(connection, "request", {"request_id": "one"})
        append_event(connection, "decision", {"outcome": "HOLD"})
        assert verify_chain(connection).valid
        connection.execute("UPDATE audit_events SET payload_json = '{}' WHERE sequence = 1")
        assert not verify_chain(connection).valid

    reorder_database = tmp_path / "reorder.db"
    with sqlite3.connect(reorder_database) as connection:
        append_event(connection, "request", {"request_id": "one"})
        append_event(connection, "decision", {"outcome": "HOLD"})
        connection.execute("UPDATE audit_events SET sequence = 3 WHERE sequence = 1")
        assert not verify_chain(connection).valid
