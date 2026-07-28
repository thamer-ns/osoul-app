"""Strict tenant-scoped journal for validated SC-V90 / bot events.

Every read and write includes the active ``user_id`` and ``portfolio_id`` in
SQL itself.  The module does not depend on a later monkey-patch of database
functions, so an early import cannot bypass tenant isolation.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import database as db
from ai_engine_core.compass_contract import parse_compass_payload
from ai_engine_core.json_utils import strict_json_dumps
from ai_engine_core.timeframe_contract import canonical_timeframe
from tenant_scope import current_tenant

LOGGER = logging.getLogger(__name__)
TABLE = "external_analysis_events"
_INSTALLED = False

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
_TERMINAL_CODES = frozenset({"T3", "SL", "C", "FO"})
_ALLOWED_PREVIOUS = {
    "T1": frozenset({"NL", "NS"}),
    "T2": frozenset({"T1"}),
    "T3": frozenset({"T2"}),
    "SL": frozenset({"NL", "NS", "T1", "T2"}),
    "C": frozenset({"NL", "NS", "T1", "T2"}),
    "FO": frozenset({"NL", "NS", "T1", "T2"}),
}


def install_external_signal_journal() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        import tenant_scope

        tenant_scope.SCOPED_TABLES.add(TABLE)
    except Exception:
        LOGGER.exception("Unable to register external event table for tenant scoping")
        raise
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        event_key TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        portfolio_id INTEGER NOT NULL,
        lifecycle_key TEXT NOT NULL,
        source TEXT NOT NULL,
        event_code TEXT NOT NULL,
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
        received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """
    if not db.execute_query(ddl):
        raise RuntimeError("تعذر إنشاء سجل أحداث المؤشر والبوت")
    statements = (
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_time ON {TABLE}(user_id, portfolio_id, event_timestamp_ms)",
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_symbol_frame ON {TABLE}(user_id, portfolio_id, symbol, timeframe)",
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_lifecycle ON {TABLE}(user_id, portfolio_id, lifecycle_key, event_timestamp_ms)",
    )
    for statement in statements:
        if not db.execute_query(statement):
            raise RuntimeError("تعذر إنشاء فهرس سجل المؤشر والبوت")
    _INSTALLED = True


def _canonical_symbol(value: Any) -> str:
    return str(value or "").strip().upper().split(":")[-1].replace(".SR", "")


def _level_identity(value: Any) -> str:
    if value is None:
        return ""
    try:
        return format(float(value), ".10g")
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _event_key(parsed: dict[str, Any], user_id: int, portfolio_id: int) -> str:
    identity = "|".join(
        (
            str(user_id), str(portfolio_id), str(parsed.get("source") or ""),
            str(parsed.get("event") or ""), str(parsed.get("symbol") or ""),
            str(parsed.get("timeframe") or ""), str(parsed.get("event_timestamp_ms") or ""),
            _level_identity(parsed.get("event_price")),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _lifecycle_key(parsed: dict[str, Any]) -> str:
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    identity = "|".join(
        (
            str(parsed.get("source") or ""),
            _canonical_symbol(parsed.get("symbol")),
            canonical_timeframe(parsed.get("timeframe")),
            str(parsed.get("direction") or "neutral"),
            _level_identity(parsed.get("entry")),
            _level_identity(parsed.get("stop")),
            *(_level_identity(value) for value in targets),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _adapt(query: str, kind: str) -> str:
    return query if kind == "postgres" else query.replace("%s", "?")


def _validate_transition(event_code: str, latest: dict[str, Any] | None, timestamp_ms: int) -> str | None:
    if latest is None:
        return None if event_code in {"NL", "NS"} else "entry_event_required"
    latest_code = str(latest.get("event_code") or "").upper()
    latest_timestamp = int(latest.get("event_timestamp_ms") or 0)
    if timestamp_ms <= latest_timestamp:
        return "stale_or_out_of_order_event"
    if event_code in {"NL", "NS"}:
        return None if latest_code in _TERMINAL_CODES else "lifecycle_already_active"
    allowed = _ALLOWED_PREVIOUS.get(event_code, frozenset())
    return None if latest_code in allowed else "invalid_lifecycle_transition"


def _record_transaction(parsed: dict[str, Any], user_id: int, portfolio_id: int) -> dict[str, Any]:
    key = _event_key(parsed, user_id, portfolio_id)
    lifecycle_key = _lifecycle_key(parsed)
    event_code = str(parsed["event"]).upper()
    timestamp_ms = int(parsed["event_timestamp_ms"])
    status = _EVENT_STATUS[event_code]
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    geometry = parsed.get("geometry") if isinstance(parsed.get("geometry"), dict) else {}
    received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn = None
    kind = ""
    try:
        conn, kind = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            _adapt(
                f"SELECT event_key FROM {TABLE} WHERE event_key=%s AND user_id=%s AND portfolio_id=%s LIMIT 1",
                kind,
            ),
            (key, user_id, portfolio_id),
        )
        if cur.fetchone() is not None:
            conn.rollback()
            return {
                "ok": True, "created": False, "duplicate": True,
                "event_key": key, "lifecycle_key": lifecycle_key,
                "lifecycle_status": status, "parsed": parsed,
            }

        lock_suffix = " FOR UPDATE" if kind == "postgres" else ""
        cur.execute(
            _adapt(
                f"SELECT event_code,event_timestamp_ms,lifecycle_status FROM {TABLE} "
                "WHERE user_id=%s AND portfolio_id=%s AND lifecycle_key=%s "
                f"ORDER BY event_timestamp_ms DESC LIMIT 1{lock_suffix}",
                kind,
            ),
            (user_id, portfolio_id, lifecycle_key),
        )
        row = cur.fetchone()
        latest = None
        if row is not None:
            latest = {
                "event_code": row[0],
                "event_timestamp_ms": row[1],
                "lifecycle_status": row[2],
            }
        transition_error = _validate_transition(event_code, latest, timestamp_ms)
        if transition_error:
            conn.rollback()
            return {
                "ok": False, "created": False, "reason": transition_error,
                "event_key": key, "lifecycle_key": lifecycle_key,
            }

        query = f"""
        INSERT INTO {TABLE} (
            event_key,user_id,portfolio_id,lifecycle_key,source,event_code,
            symbol,timeframe,direction,lifecycle_status,event_time,
            event_timestamp_ms,event_price,entry_price,stop_price,
            target1,target2,target3,confidence,geometry_valid,payload_json,received_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (event_key) DO NOTHING
        """
        cur.execute(
            _adapt(query, kind),
            (
                key, user_id, portfolio_id, lifecycle_key, parsed["source"], event_code,
                _canonical_symbol(parsed["symbol"]), parsed["timeframe"], parsed["direction"],
                status, parsed["event_time"], timestamp_ms, parsed["event_price"],
                parsed.get("entry"), parsed.get("stop"), targets[0], targets[1], targets[2],
                parsed.get("confidence"), 1 if geometry.get("valid") else 0,
                strict_json_dumps(parsed), received_at,
            ),
        )
        created = int(cur.rowcount or 0) > 0
        conn.commit()
        return {
            "ok": True, "created": created, "duplicate": not created,
            "event_key": key, "lifecycle_key": lifecycle_key,
            "lifecycle_status": status, "parsed": parsed,
        }
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                LOGGER.debug("External event rollback failed", exc_info=True)
        LOGGER.exception("Unable to record external event")
        return {"ok": False, "created": False, "reason": "database_error"}
    finally:
        if conn is not None:
            db.put_connection(conn, kind)


def record_external_event(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    tenant = current_tenant()
    if tenant is None:
        return {"ok": False, "created": False, "reason": "no_active_tenant"}
    install_external_signal_journal()
    try:
        parsed = parse_compass_payload(payload)
    except ValueError:
        LOGGER.info("Rejected invalid external analysis event", exc_info=True)
        return {"ok": False, "created": False, "reason": "invalid_payload"}
    return _record_transaction(parsed, tenant.user_id, tenant.portfolio_id)


def recent_external_events(symbol: str | None = None, timeframe: str | None = None, *, limit: int = 50) -> pd.DataFrame:
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
            frame = canonical_timeframe(timeframe)
        except ValueError:
            return pd.DataFrame()
        clauses.append("timeframe=%s")
        params.append(frame)
    safe_limit = max(1, min(500, int(limit)))
    query = (
        f"SELECT source,event_code,symbol,timeframe,direction,lifecycle_status,event_time,"
        "event_timestamp_ms,event_price,entry_price,stop_price,target1,target2,target3,"
        "confidence,geometry_valid,payload_json,received_at,lifecycle_key,event_key "
        f"FROM {TABLE} WHERE {' AND '.join(clauses)} "
        "ORDER BY event_timestamp_ms DESC LIMIT %s"
    )
    params.append(safe_limit)
    frame = db.fetch_df(query, tuple(params))
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def latest_external_event(symbol: str, timeframe: str) -> dict[str, Any] | None:
    frame = recent_external_events(symbol, timeframe, limit=1)
    return None if frame.empty else {str(key): value for key, value in frame.iloc[0].to_dict().items()}


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
        "lifecycle_key": latest.get("lifecycle_key"),
    }


__all__ = [
    "install_external_signal_journal", "latest_external_event",
    "lifecycle_snapshot", "record_external_event", "recent_external_events",
]
