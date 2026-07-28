from __future__ import annotations

import inspect

import database
from ai_engine_core import external_signal_journal_v5 as journal


def test_external_journal_reads_are_explicitly_tenant_scoped():
    source = inspect.getsource(journal.recent_external_events)
    assert '"user_id=%s"' in source
    assert '"portfolio_id=%s"' in source
    assert "fetch_table(TABLE)" not in source
    assert "import database as db" in inspect.getsource(journal)


def test_duplicate_and_lifecycle_statuses_are_not_conflated():
    assert journal._validate_transition("T1", None, 2_000) == "entry_event_required"
    assert journal._validate_transition(
        "T1", {"event_code": "NL", "event_timestamp_ms": 1_000}, 2_000
    ) is None
    assert journal._validate_transition(
        "T2", {"event_code": "NL", "event_timestamp_ms": 1_000}, 2_000
    ) == "invalid_lifecycle_transition"
    assert journal._validate_transition(
        "T1", {"event_code": "NL", "event_timestamp_ms": 2_000}, 1_500
    ) == "stale_or_out_of_order_event"
    assert journal._validate_transition(
        "NL", {"event_code": "T3", "event_timestamp_ms": 1_000}, 2_000
    ) is None


def test_lifecycle_identity_includes_plan_geometry():
    base = {
        "source": "SC-V90-D",
        "symbol": "TADAWUL:1120",
        "timeframe": "1d",
        "direction": "buy",
        "entry": 100,
        "stop": 98,
        "targets": [102, 104, 106],
    }
    changed = {**base, "entry": 101, "targets": [103, 105, 107]}
    assert journal._lifecycle_key(base) != journal._lifecycle_key(changed)


def test_postgres_pool_is_thread_safe():
    source = inspect.getsource(database)
    assert "ThreadedConnectionPool" in source
    assert "SimpleConnectionPool" not in source
    assert '"pool_type": "threaded"' in source
