from __future__ import annotations

import inspect

import pandas as pd

from ai_engine_core import external_signal_journal_v5 as journal
from tenant_scope import TenantContext


def _parsed(event: str = "NL", timestamp: int = 1_760_000_000_000):
    return {
        "schema_version": 1,
        "source": "SC-V90-I",
        "event": event,
        "symbol": "TADAWUL:1120",
        "asset_type": "stock",
        "timeframe": "5m",
        "event_time": "2025-10-09T08:53:20+00:00",
        "event_timestamp_ms": timestamp,
        "event_price": 100.0,
        "direction": "buy",
        "direction_code": 1,
        "entry": 100.0,
        "stop": 98.0,
        "targets": [102.0, 104.0, 106.0],
        "target_count": 3,
        "score": 8,
        "score_maximum": 10,
        "confidence": 80.0,
        "counter_trend": False,
        "geometry": {"valid": True},
    }


def test_journal_does_not_capture_patchable_database_functions_at_import_time():
    source = inspect.getsource(journal)
    assert "from database import" not in source
    assert "user_id=%s" in source
    assert "portfolio_id=%s" in source


def test_recent_events_always_bind_the_active_tenant(monkeypatch):
    captured = {}
    tenant = TenantContext(user_id=7, username="tenant-a", portfolio_id=11)
    monkeypatch.setattr(journal, "current_tenant", lambda: tenant)
    monkeypatch.setattr(journal, "install_external_signal_journal", lambda: None)

    def fake_fetch(query, params):
        captured["query"] = query
        captured["params"] = params
        return pd.DataFrame()

    monkeypatch.setattr(journal, "_fetch_explicit", fake_fetch)

    result = journal.recent_external_events("1120.SR", "5m", limit=25)

    assert result.empty
    assert "user_id=%s" in captured["query"]
    assert "portfolio_id=%s" in captured["query"]
    assert captured["params"][:2] == (7, 11)
    assert 7 in captured["params"] and 11 in captured["params"]


def test_duplicate_is_reported_as_existing_not_created(monkeypatch):
    tenant = TenantContext(user_id=7, username="tenant-a", portfolio_id=11)
    monkeypatch.setattr(journal, "current_tenant", lambda: tenant)
    monkeypatch.setattr(journal, "install_external_signal_journal", lambda: None)
    monkeypatch.setattr(journal, "parse_compass_payload", lambda payload: _parsed())
    monkeypatch.setattr(journal, "_event_exists", lambda *args: True)

    result = journal.record_external_event({"already": "parsed-by-test"})

    assert result["ok"] is True
    assert result["created"] is False
    assert result["reason"] == "duplicate"


def test_lifecycle_requires_initial_plan_and_monotonic_target_order():
    assert journal._validate_transition("T1", 200, None) == "missing_initial_event"

    active = {
        "lifecycle_status": "ACTIVE",
        "event_timestamp_ms": 100,
    }
    assert journal._validate_transition("T1", 200, active) is None
    assert journal._validate_transition("T2", 200, active) == "invalid_lifecycle_transition"
    assert journal._validate_transition("T1", 100, active) == "stale_or_out_of_order_event"

    target1 = {
        "lifecycle_status": "TARGET_1",
        "event_timestamp_ms": 200,
    }
    assert journal._validate_transition("T2", 300, target1) is None
    assert journal._validate_transition("T3", 300, target1) == "invalid_lifecycle_transition"

    terminal = {
        "lifecycle_status": "STOPPED",
        "event_timestamp_ms": 300,
    }
    assert journal._validate_transition("T2", 400, terminal) == "lifecycle_already_closed"
