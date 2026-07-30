"""Backward-compatible import path for the atomic tenant journal V7.

Every public operation checks the idempotent tenant migration so a T1/SL/C can
extend an NL/NS stored by V6. A migration outage does not block application
startup or read-only pages, but lifecycle writes fail closed until state is safe.
Normalized dictionaries are converted back to the compact SC wire contract.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import external_signal_journal_v7 as _impl
from .compass_contract import to_bot_wire_payload
from .external_signal_migration_v8 import migrate_current_tenant_v6_to_v7


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


def _wire_payload(payload: str | bytes | dict[str, Any]) -> str | bytes | dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    if any(key in payload for key in ("s", "e", "sy", "tf", "p")):
        return payload
    if payload.get("source") and payload.get("event"):
        return to_bot_wire_payload(payload)
    return payload


def _prepare() -> dict[str, Any]:
    _impl.install_external_signal_journal()
    return migrate_current_tenant_v6_to_v7()


def install_external_signal_journal() -> None:
    # Installation remains fail-open for authenticated application startup. The
    # write APIs below still reject lifecycle changes when migration is unsafe.
    _prepare()


def _migration_write_error(result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("ok") or result.get("reason") == "no_active_tenant":
        return None
    return {
        "ok": False,
        "created": False,
        "reason": "legacy_migration_unavailable",
        "migration_reason": result.get("reason"),
    }


def record_external_event(
    payload: str | bytes | dict[str, Any],
    *,
    remote_event_id: int | None = None,
    remote_channel: str | None = None,
) -> dict[str, Any]:
    migration = _prepare()
    blocked = _migration_write_error(migration)
    if blocked is not None:
        return blocked
    return _impl.record_external_event(
        _wire_payload(payload),
        remote_event_id=remote_event_id,
        remote_channel=remote_channel,
    )


def quarantine_remote_event(
    remote_channel: str,
    remote_event_id: int,
    payload: Any,
    reason: str,
) -> dict[str, Any]:
    migration = _prepare()
    blocked = _migration_write_error(migration)
    if blocked is not None:
        return blocked
    return _impl.quarantine_remote_event(
        remote_channel,
        remote_event_id,
        payload,
        reason,
    )


def latest_external_event(symbol: str, timeframe: str) -> dict[str, Any] | None:
    _prepare()
    return _impl.latest_external_event(symbol, timeframe)


def latest_remote_cursor(remote_channel: str) -> int:
    _prepare()
    return _impl.latest_remote_cursor(remote_channel)


def lifecycle_snapshot(symbol: str, timeframe: str) -> dict[str, Any]:
    migration = _prepare()
    snapshot = _impl.lifecycle_snapshot(symbol, timeframe)
    if not migration.get("ok") and migration.get("reason") != "no_active_tenant":
        snapshot = dict(snapshot)
        snapshot["migration_warning"] = migration.get("reason")
    return snapshot


def recent_external_events(
    symbol: str | None = None,
    timeframe: str | None = None,
    *,
    limit: int = 100,
) -> pd.DataFrame:
    _prepare()
    return _impl.recent_external_events(symbol, timeframe, limit=limit)


def recent_quarantined_events(*, limit: int = 100) -> pd.DataFrame:
    _prepare()
    return _impl.recent_quarantined_events(limit=limit)


JournalStateError = _impl.JournalStateError
QUARANTINE_TABLE = _impl.QUARANTINE_TABLE
STATE_TABLE = _impl.STATE_TABLE
TABLE = _impl.TABLE

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
