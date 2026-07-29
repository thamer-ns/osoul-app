"""Backward-compatible import path for the atomic tenant journal v7."""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import external_signal_journal_v7 as _impl


def _validate_transition(
    event_code: str,
    event_timestamp_ms: int,
    plan_key: str,
    latest: dict[str, Any] | None,
) -> str | None:
    """Keep every lifecycle, including a restarted plan, strictly monotonic."""
    if latest is None:
        return None if event_code in {"NL", "NS"} else "missing_initial_event"
    previous_time = int(
        pd.to_numeric(latest.get("last_event_timestamp_ms"), errors="coerce") or 0
    )
    if event_timestamp_ms <= previous_time:
        return "stale_or_out_of_order_event"
    status = str(latest.get("lifecycle_status") or "")
    if event_code in {"NL", "NS"}:
        return None if status in _impl._TERMINAL else "active_plan_already_exists"  # noqa: SLF001
    if str(latest.get("current_plan_key") or "") != plan_key:
        return "plan_identity_mismatch"
    if status in _impl._TERMINAL:  # noqa: SLF001
        return "lifecycle_already_closed"
    if event_code not in _impl._ALLOWED_NEXT.get(status, set()):  # noqa: SLF001
        return "invalid_lifecycle_transition"
    return None


_impl._validate_transition = _validate_transition  # noqa: SLF001

JournalStateError = _impl.JournalStateError
QUARANTINE_TABLE = _impl.QUARANTINE_TABLE
STATE_TABLE = _impl.STATE_TABLE
TABLE = _impl.TABLE
install_external_signal_journal = _impl.install_external_signal_journal
latest_external_event = _impl.latest_external_event
latest_remote_cursor = _impl.latest_remote_cursor
lifecycle_snapshot = _impl.lifecycle_snapshot
quarantine_remote_event = _impl.quarantine_remote_event
recent_external_events = _impl.recent_external_events
recent_quarantined_events = _impl.recent_quarantined_events
record_external_event = _impl.record_external_event

__all__ = [
    "JournalStateError",
    "QUARANTINE_TABLE",
    "STATE_TABLE",
    "TABLE",
    "_validate_transition",
    "install_external_signal_journal",
    "latest_external_event",
    "latest_remote_cursor",
    "lifecycle_snapshot",
    "quarantine_remote_event",
    "recent_external_events",
    "recent_quarantined_events",
    "record_external_event",
]
