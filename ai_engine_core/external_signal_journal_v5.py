"""Tenant-scoped journal for validated TradingView/bot evidence.

The journal makes SC-V90/SC-FXM integration durable inside Osoli without making
external alerts authoritative.  Each event is validated by ``compass_contract``
first, de-duplicated, stored with its lifecycle state, and later compared with
the native report.  No order execution exists in this module.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ai_engine_core.compass_contract import parse_compass_payload
from ai_engine_core.json_utils import strict_json_dumps
from database import execute_query, fetch_table
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
        event_timestamp_ms BIGINT,
        event_price REAL,
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
    if not execute_query(ddl):
        raise RuntimeError("تعذر إنشاء سجل أحداث المؤشر والبوت")
    for statement in (
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_time ON {TABLE}(user_id, portfolio_id, event_time)",
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_symbol_frame ON {TABLE}(user_id, portfolio_id, symbol, timeframe)",
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_lifecycle ON {TABLE}(user_id, portfolio_id, lifecycle_key, lifecycle_status)",
    ):
        if not execute_query(statement):
            raise RuntimeError("تعذر إنشاء فهرس سجل المؤشر والبوت")
    _INSTALLED = True


def _canonical_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper().split(":")[-1]
    return symbol.replace(".SR", "")


def _event_key(parsed: dict[str, Any], user_id: int, portfolio_id: int) -> str:
    identity = "|".join(
        (
            str(user_id),
            str(portfolio_id),
            str(parsed.get("source") or ""),
            str(parsed.get("event") or ""),
            str(parsed.get("symbol") or ""),
            str(parsed.get("timeframe") or ""),
            str(parsed.get("event_timestamp_ms") or ""),
            str(parsed.get("event_price") or ""),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _lifecycle_key(parsed: dict[str, Any]) -> str:
    direction = str(parsed.get("direction") or "neutral")
    return "|".join(
        (
            str(parsed.get("source") or ""),
            _canonical_symbol(parsed.get("symbol")),
            str(parsed.get("timeframe") or ""),
            direction,
        )
    )


def record_external_event(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    tenant = current_tenant()
    if tenant is None:
        return {"ok": False, "reason": "no_active_tenant"}
    install_external_signal_journal()
    try:
        parsed = parse_compass_payload(payload)
    except ValueError:
        LOGGER.info("Rejected invalid external analysis event", exc_info=True)
        return {"ok": False, "reason": "invalid_payload"}
    event_code = str(parsed.get("event") or "").strip().upper()
    status = _EVENT_STATUS.get(event_code)
    if status is None:
        return {"ok": False, "reason": "unsupported_event"}
    lifecycle_key = _lifecycle_key(parsed)
    key = _event_key(parsed, tenant.user_id, tenant.portfolio_id)
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    geometry = parsed.get("geometry") if isinstance(parsed.get("geometry"), dict) else {}
    received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    query = f"""
    INSERT INTO {TABLE} (
        event_key, user_id, portfolio_id, lifecycle_key, source, event_code,
        symbol, timeframe, direction, lifecycle_status, event_time,
        event_timestamp_ms, event_price, entry_price, stop_price,
        target1, target2, target3, confidence, geometry_valid,
        payload_json, received_at
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (event_key) DO NOTHING
    """
    ok = execute_query(
        query,
        (
            key,
            tenant.user_id,
            tenant.portfolio_id,
            lifecycle_key,
            parsed.get("source"),
            event_code,
            _canonical_symbol(parsed.get("symbol")),
            parsed.get("timeframe"),
            parsed.get("direction"),
            status,
            parsed.get("event_time"),
            parsed.get("event_timestamp_ms"),
            parsed.get("event_price"),
            parsed.get("entry"),
            parsed.get("stop"),
            targets[0],
            targets[1],
            targets[2],
            parsed.get("confidence"),
            1 if geometry.get("valid") else 0,
            strict_json_dumps(parsed),
            received_at,
        ),
    )
    return {
        "ok": bool(ok),
        "created": bool(ok),
        "event_key": key,
        "lifecycle_key": lifecycle_key,
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
    try:
        frame = fetch_table(TABLE)
    except Exception:
        LOGGER.exception("Unable to read external signal journal")
        return pd.DataFrame()
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    filtered = frame.copy()
    if symbol and "symbol" in filtered.columns:
        filtered = filtered[
            filtered["symbol"].astype(str).map(_canonical_symbol)
            == _canonical_symbol(symbol)
        ]
    if timeframe and "timeframe" in filtered.columns:
        filtered = filtered[
            filtered["timeframe"].astype(str).str.strip().str.lower()
            == str(timeframe).strip().lower()
        ]
    if "event_timestamp_ms" in filtered.columns:
        filtered["_order"] = pd.to_numeric(
            filtered["event_timestamp_ms"], errors="coerce"
        ).fillna(0)
    else:
        filtered["_order"] = pd.to_datetime(
            filtered.get("received_at"), errors="coerce", utc=True
        ).astype("int64", errors="ignore")
    filtered = filtered.sort_values("_order", ascending=False).head(
        max(1, min(500, int(limit)))
    )
    columns = [
        "source",
        "event_code",
        "symbol",
        "timeframe",
        "direction",
        "lifecycle_status",
        "event_time",
        "event_price",
        "entry_price",
        "stop_price",
        "target1",
        "target2",
        "target3",
        "confidence",
        "geometry_valid",
        "payload_json",
        "received_at",
        "lifecycle_key",
    ]
    return filtered[[column for column in columns if column in filtered.columns]].reset_index(drop=True)


def latest_external_event(
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
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
        "lifecycle_key": latest.get("lifecycle_key"),
    }


__all__ = [
    "install_external_signal_journal",
    "latest_external_event",
    "lifecycle_snapshot",
    "record_external_event",
    "recent_external_events",
]
