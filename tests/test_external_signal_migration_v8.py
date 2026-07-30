from __future__ import annotations

import sqlite3

from ai_engine_core import external_signal_journal_v7 as implementation
from ai_engine_core import external_signal_migration_v8 as migration
from tenant_scope import TenantContext


def test_v6_active_plan_is_migrated_with_v7_state(monkeypatch, tmp_path):
    path = tmp_path / "journal-migration.sqlite3"
    tenant = TenantContext(user_id=7, username="tenant-a", portfolio_id=11)

    def get_connection():
        return sqlite3.connect(path, timeout=10, check_same_thread=False), "sqlite"

    def put_connection(conn, kind):
        assert kind == "sqlite"
        conn.close()

    def execute_query(query, params=None):
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        try:
            conn.execute(query, params or ())
            conn.commit()
            return True
        finally:
            conn.close()

    monkeypatch.setattr(implementation.database, "get_connection", get_connection)
    monkeypatch.setattr(implementation.database, "put_connection", put_connection)
    monkeypatch.setattr(implementation.database, "execute_query", execute_query)
    monkeypatch.setattr(migration, "current_tenant", lambda: tenant)
    implementation._INSTALLED = False
    migration._DONE.clear()

    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE external_analysis_events_v6 (
            event_key TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            portfolio_id INTEGER NOT NULL,
            plan_key TEXT NOT NULL,
            source TEXT NOT NULL,
            event_code TEXT NOT NULL,
            event_rank INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            direction TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            event_time TEXT NOT NULL,
            event_timestamp_ms BIGINT NOT NULL,
            event_price REAL NOT NULL,
            entry_price REAL,
            stop_price REAL,
            target1 REAL,
            target2 REAL,
            target3 REAL,
            confidence REAL,
            geometry_valid INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            remote_event_id BIGINT,
            remote_channel TEXT,
            received_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO external_analysis_events_v6(
            event_key,user_id,portfolio_id,plan_key,source,event_code,event_rank,
            symbol,timeframe,direction,lifecycle_status,event_time,event_timestamp_ms,
            event_price,entry_price,stop_price,target1,target2,target3,confidence,
            geometry_valid,payload_json,remote_event_id,remote_channel,received_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "event-1",
            7,
            11,
            "plan-1",
            "SC-V90-D",
            "NL",
            0,
            "TADAWUL:1120",
            "1d",
            "buy",
            "ACTIVE",
            "2026-01-01T12:00:00+00:00",
            1_767_268_800_000,
            100.0,
            100.0,
            98.0,
            102.0,
            104.0,
            106.0,
            80.0,
            1,
            "{}",
            None,
            None,
            "2026-01-01T12:00:01+00:00",
        ),
    )
    conn.commit()
    conn.close()

    implementation.install_external_signal_journal()
    result = migration.migrate_current_tenant_v6_to_v7()

    assert result["ok"] is True
    assert result["migrated"] == 1

    conn = sqlite3.connect(path)
    event = conn.execute(
        "SELECT event_key,scope_key,symbol,timeframe,lifecycle_status "
        "FROM external_analysis_events_v7"
    ).fetchone()
    state = conn.execute(
        "SELECT current_plan_key,lifecycle_status,last_event_code "
        "FROM external_analysis_plan_state_v7"
    ).fetchone()
    marker = conn.execute(
        "SELECT migrated_rows FROM external_signal_migrations_v8"
    ).fetchone()
    conn.close()

    assert event is not None
    assert event[0] == "event-1"
    assert len(event[1]) == 64
    assert event[2:] == ("1120", "1d", "ACTIVE")
    assert state == ("plan-1", "ACTIVE", "NL")
    assert marker == (1,)
