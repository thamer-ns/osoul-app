"""Tenant-isolated, ordered journal for SC-V90 and market-bot events.

Version 6 deliberately avoids module-level imports of patchable database
functions.  Every read carries ``user_id`` and ``portfolio_id`` in the SQL
itself, every insert reports its actual row count, and lifecycle updates are
accepted only in chronological order after a valid initial plan.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import database
from ai_engine_core.compass_contract import normalise_timeframe, parse_compass_payload
from ai_engine_core.json_utils import strict_json_dumps
from database_write_v6 import execute_write
from tenant_scope import current_tenant

LOGGER = logging.getLogger(__name__)
TABLE = "external_analysis_events_v6"
_INSTALLED = False
_INSTALL_LOCK = threading.RLock()
_EVENT_LOCK = threading.RLock()

_EVENT_STATUS = {
    "NL": "ACTIVE",
    "NS": "ACTIVE",
    "T1": "TARGET_1",
    "T2": "TARGET_2",
    "T3": "TARGET_3",
    "SL": "STOPPED",
    "C": "CANCELLED",
    "FO": "FAKEOUT",
}
_EVENT_RANK = {"NL": 0, "NS": 0, "T1": 1, "T2": 2, "T3": 3, "SL": 90, "C": 91, "FO": 92}
_TERMINAL = {"TARGET_3", "STOPPED", "CANCELLED", "FAKEOUT"}
_ALLOWED_NEXT = {
    "ACTIVE": {"T1", "SL", "C", "FO"},
    "TARGET_1": {"T2", "SL", "C", "FO"},
    "TARGET_2": {"T3", "SL", "C", "FO"},
}


def _fetch_explicit(query: str, params: tuple[Any, ...]) -> pd.DataFrame:
    """Execute one explicit tenant-filtered read without relying on monkeypatches."""
    conn = None
    kind = ""
    try:
        conn, kind = database.get_connection()
        adapted = database._adapt_query_for_kind(query, kind)  # noqa: SLF001
        return pd.read_sql(adapted, conn, params=params)
    except Exception:
        LOGGER.exception("Explicit external-journal read failed")
        return pd.DataFrame()
    finally:
        if conn is not None:
            database.put_connection(conn, kind)


def install_external_signal_journal() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import tenant_scope

        tenant_scope.SCOPED_TABLES.add(TABLE)
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
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
            received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
        if not database.execute_query(ddl):
            raise RuntimeError("تعذر إنشاء سجل أحداث المؤشر والبوت الآمن")
        statements = (
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_time ON {TABLE}(user_id, portfolio_id, event_timestamp_ms)",
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_plan ON {TABLE}(user_id, portfolio_id, plan_key, event_timestamp_ms)",
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_symbol ON {TABLE}(user_id, portfolio_id, symbol, timeframe)",
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_remote ON {TABLE}(user_id, portfolio_id, remote_channel, remote_event_id)",
        )
        for statement in statements:
            if not database.execute_query(statement):
                raise RuntimeError("تعذر إنشاء فهرس سجل المؤشر والبوت")
        _INSTALLED = True


def _canonical_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper().split(":")[-1]
    return symbol.replace(".SR", "")


def _levels(parsed: dict[str, Any]) -> tuple[Any, ...]:
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    return parsed.get("entry"), parsed.get("stop"), targets[0], targets[1], targets[2]


def _plan_key(parsed: dict[str, Any]) -> str:
    entry, stop, target1, target2, target3 = _levels(parsed)
    identity = "|".join(
        (
            str(parsed.get("source") or ""),
            _canonical_symbol(parsed.get("symbol")),
            str(parsed.get("timeframe") or ""),
            str(parsed.get("direction") or "neutral"),
            str(entry),
            str(stop),
            str(target1),
            str(target2),
            str(target3),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _event_key(parsed: dict[str, Any], user_id: int, portfolio_id: int) -> str:
    identity = "|".join(
        (
            str(user_id),
            str(portfolio_id),
            _plan_key(parsed),
            str(parsed.get("event") or ""),
            str(parsed.get("event_timestamp_ms") or ""),
            str(parsed.get("event_price") or ""),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _event_exists(event_key: str, user_id: int, portfolio_id: int) -> bool:
    frame = _fetch_explicit(
        f"SELECT event_key FROM {TABLE} WHERE event_key=%s AND user_id=%s AND portfolio_id=%s LIMIT 1",
        (event_key, user_id, portfolio_id),
    )
    return not frame.empty


def _latest_plan_event(plan_key: str, user_id: int, portfolio_id: int) -> dict[str, Any] | None:
    frame = _fetch_explicit(
        f"SELECT event_code,lifecycle_status,event_timestamp_ms,event_key "
        f"FROM {TABLE} WHERE user_id=%s AND portfolio_id=%s AND plan_key=%s "
        "ORDER BY event_timestamp_ms DESC, received_at DESC LIMIT 1",
        (user_id, portfolio_id, plan_key),
    )
    if frame.empty:
        return None
    return {str(key): value for key, value in frame.iloc[0].to_dict().items()}


def _validate_transition(
    event_code: str,
    event_timestamp_ms: int,
    latest: dict[str, Any] | None,
) -> str | None:
    if event_code == "FO" and latest is None:
        return None
    if event_code in {"NL", "NS"}:
        if latest is None or str(latest.get("lifecycle_status")) in _TERMINAL:
            return None
        return "active_plan_already_exists"
    if latest is None:
        return "missing_initial_event"
    previous_time = int(pd.to_numeric(latest.get("event_timestamp_ms"), errors="coerce") or 0)
    if event_timestamp_ms <= previous_time:
        return "stale_or_out_of_order_event"
    status = str(latest.get("lifecycle_status") or "")
    if status in _TERMINAL:
        return "lifecycle_already_closed"
    if event_code not in _ALLOWED_NEXT.get(status, set()):
        return "invalid_lifecycle_transition"
    return None


def record_external_event(
    payload: str | bytes | dict[str, Any],
    *,
    remote_event_id: int | None = None,
    remote_channel: str | None = None,
) -> dict[str, Any]:
    tenant = current_tenant()
    if tenant is None:
        return {"ok": False, "created": False, "reason": "no_active_tenant"}
    install_external_signal_journal()
    try:
        parsed = parse_compass_payload(payload)
    except ValueError:
        LOGGER.info("Rejected invalid external analysis event", exc_info=True)
        return {"ok": False, "created": False, "reason": "invalid_payload"}

    event_code = str(parsed.get("event") or "").strip().upper()
    status = _EVENT_STATUS.get(event_code)
    if status is None:
        return {"ok": False, "created": False, "reason": "unsupported_event"}
    channel = str(remote_channel or "").strip().lower() or None
    if channel is not None and re.fullmatch(r"[a-f0-9]{64}", channel) is None:
        return {"ok": False, "created": False, "reason": "invalid_remote_channel"}
    if remote_event_id is not None and int(remote_event_id) <= 0:
        return {"ok": False, "created": False, "reason": "invalid_remote_event_id"}

    plan_key = _plan_key(parsed)
    key = _event_key(parsed, tenant.user_id, tenant.portfolio_id)
    event_time_ms = int(parsed["event_timestamp_ms"])
    entry, stop, target1, target2, target3 = _levels(parsed)
    geometry = parsed.get("geometry") if isinstance(parsed.get("geometry"), dict) else {}
    received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with _EVENT_LOCK:
        if _event_exists(key, tenant.user_id, tenant.portfolio_id):
            return {
                "ok": True,
                "created": False,
                "reason": "duplicate",
                "event_key": key,
                "plan_key": plan_key,
                "lifecycle_status": status,
                "parsed": parsed,
            }
        latest = _latest_plan_event(plan_key, tenant.user_id, tenant.portfolio_id)
        transition_error = _validate_transition(event_code, event_time_ms, latest)
        if transition_error:
            return {
                "ok": False,
                "created": False,
                "reason": transition_error,
                "event_key": key,
                "plan_key": plan_key,
                "parsed": parsed,
            }
        query = f"""
        INSERT INTO {TABLE} (
            event_key,user_id,portfolio_id,plan_key,source,event_code,event_rank,
            symbol,timeframe,direction,lifecycle_status,event_time,event_timestamp_ms,
            event_price,entry_price,stop_price,target1,target2,target3,confidence,
            geometry_valid,payload_json,remote_event_id,remote_channel,received_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (event_key) DO NOTHING
        """
        result = execute_write(
            query,
            (
                key,
                tenant.user_id,
                tenant.portfolio_id,
                plan_key,
                parsed.get("source"),
                event_code,
                _EVENT_RANK[event_code],
                _canonical_symbol(parsed.get("symbol")),
                parsed.get("timeframe"),
                parsed.get("direction"),
                status,
                parsed.get("event_time"),
                event_time_ms,
                parsed.get("event_price"),
                entry,
                stop,
                target1,
                target2,
                target3,
                parsed.get("confidence"),
                1 if geometry.get("valid") else 0,
                strict_json_dumps(parsed),
                int(remote_event_id) if remote_event_id is not None else None,
                channel,
                received_at,
            ),
        )
    if not result.ok:
        return {"ok": False, "created": False, "reason": result.reason or "database_write_failed"}
    created = result.rowcount == 1
    return {
        "ok": True,
        "created": created,
        "reason": None if created else "duplicate",
        "event_key": key,
        "plan_key": plan_key,
        "lifecycle_status": status,
        "parsed": parsed,
    }


def recent_external_events(
    symbol: str | None = None,
    timeframe: str | None = None,
    *,
    limit: int = 50,
) -> pd.DataFrame:
    tenant = current_tenant()
    if tenant is None:
        return pd.DataFrame()
    install_external_signal_journal()
    clauses = ["user_id=%s", "portfolio_id=%s"]
    params: list[Any] = [tenant.user_id, tenant.portfolio_id]
    if symbol:
        clauses.append("symbol=%s")
        params.append(_canonical_symbol(symbol))
    if timeframe:
        try:
            canonical_frame = normalise_timeframe(timeframe)
        except ValueError:
            return pd.DataFrame()
        clauses.append("timeframe=%s")
        params.append(canonical_frame)
    safe_limit = max(1, min(500, int(limit)))
    frame = _fetch_explicit(
        f"SELECT source,event_code,symbol,timeframe,direction,lifecycle_status,event_time,"
        "event_timestamp_ms,event_price,entry_price,stop_price,target1,target2,target3,"
        "confidence,geometry_valid,payload_json,received_at,plan_key,remote_event_id,remote_channel "
        f"FROM {TABLE} WHERE {' AND '.join(clauses)} "
        f"ORDER BY event_timestamp_ms DESC, received_at DESC LIMIT {safe_limit}",
        tuple(params),
    )
    return frame.reset_index(drop=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def latest_external_event(symbol: str, timeframe: str) -> dict[str, Any] | None:
    frame = recent_external_events(symbol, timeframe, limit=1)
    if frame.empty:
        return None
    return {str(key): value for key, value in frame.iloc[0].to_dict().items()}


def lifecycle_snapshot(symbol: str, timeframe: str) -> dict[str, Any]:
    frame = recent_external_events(symbol, timeframe, limit=100)
    if frame.empty:
        return {"available": False, "events": 0}
    latest = frame.iloc[0].to_dict()
    return {
        "available": True,
        "events": int(len(frame)),
        "source": latest.get("source"),
        "event": latest.get("event_code"),
        "status": latest.get("lifecycle_status"),
        "direction": latest.get("direction"),
        "event_time": latest.get("event_time"),
        "entry": latest.get("entry_price"),
        "stop": latest.get("stop_price"),
        "targets": [latest.get("target1"), latest.get("target2"), latest.get("target3")],
        "confidence": latest.get("confidence"),
        "geometry_valid": bool(latest.get("geometry_valid")),
        "plan_key": latest.get("plan_key"),
    }


def latest_remote_cursor(remote_channel: str) -> int:
    tenant = current_tenant()
    channel = str(remote_channel or "").strip().lower()
    if tenant is None or re.fullmatch(r"[a-f0-9]{64}", channel) is None:
        return 0
    install_external_signal_journal()
    frame = _fetch_explicit(
        f"SELECT MAX(remote_event_id) AS cursor FROM {TABLE} "
        "WHERE user_id=%s AND portfolio_id=%s AND remote_channel=%s",
        (tenant.user_id, tenant.portfolio_id, channel),
    )
    if frame.empty:
        return 0
    value = pd.to_numeric(frame.iloc[0].get("cursor"), errors="coerce")
    return int(value) if pd.notna(value) and int(value) > 0 else 0


__all__ = [
    "install_external_signal_journal",
    "latest_external_event",
    "latest_remote_cursor",
    "lifecycle_snapshot",
    "record_external_event",
    "recent_external_events",
]
