from __future__ import annotations

import inspect
import sqlite3

import pandas as pd

from ai_engine_core import external_signal_journal_v5 as journal
from ai_engine_core import external_signal_journal_v7 as implementation
from tenant_scope import TenantContext


def _parsed(
    event: str = "NL",
    timestamp: int = 1_760_000_000_000,
    *,
    symbol: str = "TADAWUL:1120",
    entry: float = 100.0,
    stop: float = 98.0,
    targets: tuple[float, float, float] = (102.0, 104.0, 106.0),
):
    return {
        "schema_version": 1,
        "source": "SC-V90-I",
        "event": event,
        "symbol": symbol,
        "asset_type": "stock",
        "timeframe": "5m",
        "event_time": "2025-10-09T08:53:20+00:00",
        "event_timestamp_ms": timestamp,
        "event_price": entry,
        "direction": "buy",
        "direction_code": 1,
        "entry": entry,
        "stop": stop,
        "targets": list(targets),
        "target_count": 3,
        "score": 8,
        "score_maximum": 10,
        "confidence": 80.0,
        "counter_trend": False,
        "geometry": {"valid": True},
    }


def _sqlite_backend(monkeypatch, tmp_path):
    path = tmp_path / "journal-v7.sqlite3"
    tenant = TenantContext(user_id=7, username="tenant-a", portfolio_id=11)

    def get_connection():
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        return conn, "sqlite"

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
    monkeypatch.setattr(implementation, "current_tenant", lambda: tenant)
    monkeypatch.setattr(implementation, "parse_compass_payload", lambda payload: dict(payload))
    implementation._INSTALLED = False
    implementation.install_external_signal_journal()
    return path, tenant


def test_journal_uses_database_transaction_locks_and_explicit_tenant_scope():
    source = inspect.getsource(implementation)
    assert "from database import" not in source
    assert "pg_advisory_xact_lock" in source
    assert "BEGIN IMMEDIATE" in source
    assert "PRIMARY KEY(user_id, portfolio_id, symbol, timeframe)" in source
    assert "user_id=%s" in source
    assert "portfolio_id=%s" in source


def test_recent_events_always_bind_the_active_tenant(monkeypatch):
    captured = {}
    tenant = TenantContext(user_id=7, username="tenant-a", portfolio_id=11)
    monkeypatch.setattr(implementation, "current_tenant", lambda: tenant)
    monkeypatch.setattr(implementation, "install_external_signal_journal", lambda: None)

    def fake_fetch(query, params, **kwargs):
        captured["query"] = query
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(implementation, "_fetch_explicit", fake_fetch)
    result = implementation.recent_external_events("1120.SR", "5m", limit=25)

    assert result.empty
    assert "user_id=%s" in captured["query"]
    assert "portfolio_id=%s" in captured["query"]
    assert captured["params"][:2] == (7, 11)


def test_one_active_plan_per_symbol_and_timeframe_even_when_geometry_changes(
    monkeypatch,
    tmp_path,
):
    _sqlite_backend(monkeypatch, tmp_path)
    first = implementation.record_external_event(_parsed(timestamp=1_000))
    conflicting = implementation.record_external_event(
        _parsed(timestamp=2_000, entry=101.0, stop=99.0, targets=(103.0, 105.0, 107.0))
    )
    mismatched_update = implementation.record_external_event(
        _parsed(
            event="T1",
            timestamp=2_100,
            entry=101.0,
            stop=99.0,
            targets=(103.0, 105.0, 107.0),
        )
    )

    assert first["ok"] is True and first["created"] is True
    assert conflicting["ok"] is False
    assert conflicting["reason"] == "active_plan_already_exists"
    assert mismatched_update["ok"] is False
    assert mismatched_update["reason"] == "plan_identity_mismatch"


def test_fakeout_requires_a_plan_and_restart_must_be_newer(monkeypatch, tmp_path):
    _sqlite_backend(monkeypatch, tmp_path)
    standalone = implementation.record_external_event(
        _parsed(event="FO", timestamp=900, symbol="TADAWUL:1150")
    )
    implementation.record_external_event(_parsed(timestamp=1_000))
    stopped = implementation.record_external_event(_parsed(event="SL", timestamp=2_000))
    stale_restart = implementation.record_external_event(
        _parsed(timestamp=1_500, entry=101.0, stop=99.0, targets=(103.0, 105.0, 107.0))
    )
    valid_restart = implementation.record_external_event(
        _parsed(timestamp=3_000, entry=101.0, stop=99.0, targets=(103.0, 105.0, 107.0))
    )

    assert standalone["reason"] == "missing_initial_event"
    assert stopped["ok"] is True
    assert stale_restart["reason"] == "stale_or_out_of_order_event"
    assert valid_restart["ok"] is True and valid_restart["created"] is True


def test_state_read_or_transaction_failure_is_fail_closed(monkeypatch):
    tenant = TenantContext(user_id=7, username="tenant-a", portfolio_id=11)
    monkeypatch.setattr(implementation, "current_tenant", lambda: tenant)
    monkeypatch.setattr(implementation, "install_external_signal_journal", lambda: None)
    monkeypatch.setattr(implementation, "parse_compass_payload", lambda payload: _parsed())

    def fail_connection():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(implementation.database, "get_connection", fail_connection)
    result = implementation.record_external_event({"payload": "ignored"})

    assert result["ok"] is False
    assert result["created"] is False
    assert result["reason"] == "database_state_unavailable"


def test_strict_transition_policy_rejects_old_restart_and_out_of_order_targets():
    active = {
        "current_plan_key": "plan-a",
        "lifecycle_status": "ACTIVE",
        "last_event_timestamp_ms": 100,
    }
    terminal = {
        "current_plan_key": "plan-a",
        "lifecycle_status": "STOPPED",
        "last_event_timestamp_ms": 300,
    }
    assert journal._validate_transition("FO", 200, "plan-a", None) == "missing_initial_event"
    assert journal._validate_transition("T1", 200, "plan-a", active) is None
    assert journal._validate_transition("T2", 200, "plan-a", active) == "invalid_lifecycle_transition"
    assert journal._validate_transition("T1", 200, "plan-b", active) == "plan_identity_mismatch"
    assert journal._validate_transition("NL", 200, "plan-b", active) == "active_plan_already_exists"
    assert journal._validate_transition("NL", 300, "plan-b", terminal) == "stale_or_out_of_order_event"
    assert journal._validate_transition("NL", 400, "plan-b", terminal) is None
