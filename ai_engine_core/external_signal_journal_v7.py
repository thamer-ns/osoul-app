"""Atomic tenant-isolated lifecycle journal for SC and market-bot events.

Version 7 makes the database transaction—not a process-local lock—the source of
truth.  One active plan is allowed per tenant, symbol and timeframe regardless
of source, direction or geometry.  PostgreSQL uses a transaction-scoped
advisory lock and SQLite uses ``BEGIN IMMEDIATE``.  Remote events that cannot be
accepted are quarantined so one bad event cannot block the synchronization
cursor forever.
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
TABLE = "external_analysis_events_v7"
STATE_TABLE = "external_analysis_plan_state_v7"
QUARANTINE_TABLE = "external_sync_quarantine_v7"
_INSTALLED = False
_INSTALL_LOCK = threading.RLock()
_LOCAL_EVENT_LOCK = threading.RLock()

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
_EVENT_RANK = {
    "NL": 0,
    "NS": 0,
    "T1": 1,
    "T2": 2,
    "T3": 3,
    "SL": 90,
    "C": 91,
    "FO": 92,
}
_TERMINAL = {"TARGET_3", "STOPPED", "CANCELLED", "FAKEOUT"}
_ALLOWED_NEXT = {
    "ACTIVE": {"T1", "SL", "C", "FO"},
    "TARGET_1": {"T2", "SL", "C", "FO"},
    "TARGET_2": {"T3", "SL", "C", "FO"},
}


class JournalStateError(RuntimeError):
    """Raised when lifecycle state cannot be read safely."""


def _adapt(query: str, kind: str) -> str:
    return database._adapt_query_for_kind(query, kind)  # noqa: SLF001


def _canonical_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper().split(":")[-1]
    return symbol.replace(".SR", "")


def _levels(parsed: dict[str, Any]) -> tuple[Any, ...]:
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    return parsed.get("entry"), parsed.get("stop"), targets[0], targets[1], targets[2]


def _number_identity(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return format(float(value), ".12g")
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _plan_key(parsed: dict[str, Any]) -> str:
    entry, stop, target1, target2, target3 = _levels(parsed)
    identity = "|".join(
        (
            str(parsed.get("source") or ""),
            _canonical_symbol(parsed.get("symbol")),
            str(parsed.get("timeframe") or ""),
            str(parsed.get("direction") or "neutral"),
            _number_identity(entry),
            _number_identity(stop),
            _number_identity(target1),
            _number_identity(target2),
            _number_identity(target3),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _scope_identity(user_id: int, portfolio_id: int, symbol: str, timeframe: str) -> str:
    return f"{int(user_id)}|{int(portfolio_id)}|{symbol}|{timeframe}"


def _scope_key(user_id: int, portfolio_id: int, symbol: str, timeframe: str) -> str:
    return hashlib.sha256(
        _scope_identity(user_id, portfolio_id, symbol, timeframe).encode("utf-8")
    ).hexdigest()


def _advisory_lock_key(scope_identity: str) -> int:
    return int.from_bytes(
        hashlib.sha256(scope_identity.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )


def _event_key(parsed: dict[str, Any], user_id: int, portfolio_id: int) -> str:
    identity = "|".join(
        (
            str(user_id),
            str(portfolio_id),
            _plan_key(parsed),
            str(parsed.get("event") or ""),
            str(parsed.get("event_timestamp_ms") or ""),
            _number_identity(parsed.get("event_price")),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    columns = [str(item[0]) for item in (cursor.description or [])]
    return dict(zip(columns, row, strict=False))


def _fetch_explicit(
    query: str,
    params: tuple[Any, ...],
    *,
    fail_closed: bool = False,
) -> pd.DataFrame:
    conn = None
    kind = ""
    try:
        conn, kind = database.get_connection()
        return pd.read_sql(_adapt(query, kind), conn, params=params)
    except Exception as exc:
        LOGGER.exception("Explicit external-journal read failed")
        if fail_closed:
            raise JournalStateError("external_journal_read_failed") from exc
        output = pd.DataFrame()
        output.attrs["read_error"] = True
        return output
    finally:
        if conn is not None:
            database.put_connection(conn, kind)


def _execute_ddl(statement: str, error_message: str) -> None:
    if not database.execute_query(statement):
        raise RuntimeError(error_message)


def install_external_signal_journal() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import tenant_scope

        tenant_scope.SCOPED_TABLES.update({TABLE, STATE_TABLE, QUARANTINE_TABLE})
        _execute_ddl(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                event_key TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                portfolio_id INTEGER NOT NULL,
                scope_key TEXT NOT NULL,
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
            """,
            "تعذر إنشاء سجل أحداث المؤشر والبوت V7",
        )
        _execute_ddl(
            f"""
            CREATE TABLE IF NOT EXISTS {STATE_TABLE} (
                user_id INTEGER NOT NULL,
                portfolio_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                current_plan_key TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL,
                last_event_code TEXT NOT NULL,
                last_event_timestamp_ms BIGINT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, portfolio_id, symbol, timeframe)
            )
            """,
            "تعذر إنشاء حالة خطط المؤشر والبوت V7",
        )
        _execute_ddl(
            f"""
            CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
                user_id INTEGER NOT NULL,
                portfolio_id INTEGER NOT NULL,
                remote_channel TEXT NOT NULL,
                remote_event_id BIGINT NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                quarantined_at TEXT NOT NULL,
                PRIMARY KEY(user_id, portfolio_id, remote_channel, remote_event_id)
            )
            """,
            "تعذر إنشاء حجر أحداث المزامنة V7",
        )
        statements = (
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_time ON {TABLE}(user_id, portfolio_id, event_timestamp_ms)",
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_scope ON {TABLE}(user_id, portfolio_id, symbol, timeframe, event_timestamp_ms)",
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tenant_plan ON {TABLE}(user_id, portfolio_id, plan_key, event_timestamp_ms)",
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE}_remote_unique ON {TABLE}(user_id, portfolio_id, remote_channel, remote_event_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{STATE_TABLE}_active ON {STATE_TABLE}(user_id, portfolio_id, lifecycle_status, updated_at)",
            f"CREATE INDEX IF NOT EXISTS idx_{QUARANTINE_TABLE}_tenant_time ON {QUARANTINE_TABLE}(user_id, portfolio_id, quarantined_at)",
        )
        for statement in statements:
            _execute_ddl(statement, "تعذر إنشاء فهرس سجل المؤشر والبوت V7")
        _INSTALLED = True


def _validate_transition(
    event_code: str,
    event_timestamp_ms: int,
    plan_key: str,
    latest: dict[str, Any] | None,
) -> str | None:
    if event_code in {"NL", "NS"}:
        if latest is None or str(latest.get("lifecycle_status") or "") in _TERMINAL:
            return None
        return "active_plan_already_exists"
    if latest is None:
        return "missing_initial_event"
    if str(latest.get("current_plan_key") or "") != plan_key:
        return "plan_identity_mismatch"
    previous_time = int(pd.to_numeric(latest.get("last_event_timestamp_ms"), errors="coerce") or 0)
    if event_timestamp_ms <= previous_time:
        return "stale_or_out_of_order_event"
    status = str(latest.get("lifecycle_status") or "")
    if status in _TERMINAL:
        return "lifecycle_already_closed"
    if event_code not in _ALLOWED_NEXT.get(status, set()):
        return "invalid_lifecycle_transition"
    return None


def _begin_locked_transaction(
    conn: Any,
    kind: str,
    scope_identity: str,
) -> Any:
    cursor = conn.cursor()
    if kind == "sqlite":
        cursor.execute("BEGIN IMMEDIATE")
    else:
        try:
            conn.autocommit = False
        except Exception:
            LOGGER.debug("Unable to set PostgreSQL autocommit explicitly", exc_info=True)
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (_advisory_lock_key(scope_identity),),
        )
    return cursor


def _load_state(
    cursor: Any,
    kind: str,
    user_id: int,
    portfolio_id: int,
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    query = (
        f"SELECT current_plan_key,lifecycle_status,last_event_code,last_event_timestamp_ms "
        f"FROM {STATE_TABLE} WHERE user_id=%s AND portfolio_id=%s AND symbol=%s AND timeframe=%s"
    )
    if kind == "postgres":
        query += " FOR UPDATE"
    cursor.execute(
        _adapt(query, kind),
        (user_id, portfolio_id, symbol, timeframe),
    )
    return _row_dict(cursor, cursor.fetchone())


def _event_exists_in_transaction(
    cursor: Any,
    kind: str,
    event_key: str,
    user_id: int,
    portfolio_id: int,
) -> bool:
    cursor.execute(
        _adapt(
            f"SELECT event_key FROM {TABLE} WHERE event_key=%s AND user_id=%s AND portfolio_id=%s LIMIT 1",
            kind,
        ),
        (event_key, user_id, portfolio_id),
    )
    return cursor.fetchone() is not None


def _upsert_state(
    cursor: Any,
    kind: str,
    *,
    user_id: int,
    portfolio_id: int,
    symbol: str,
    timeframe: str,
    scope_key: str,
    plan_key: str,
    lifecycle_status: str,
    event_code: str,
    event_timestamp_ms: int,
    updated_at: str,
) -> None:
    query = f"""
        INSERT INTO {STATE_TABLE}(
            user_id,portfolio_id,symbol,timeframe,scope_key,current_plan_key,
            lifecycle_status,last_event_code,last_event_timestamp_ms,updated_at
        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(user_id,portfolio_id,symbol,timeframe) DO UPDATE SET
            scope_key=excluded.scope_key,
            current_plan_key=excluded.current_plan_key,
            lifecycle_status=excluded.lifecycle_status,
            last_event_code=excluded.last_event_code,
            last_event_timestamp_ms=excluded.last_event_timestamp_ms,
            updated_at=excluded.updated_at
    """
    cursor.execute(
        _adapt(query, kind),
        (
            user_id,
            portfolio_id,
            symbol,
            timeframe,
            scope_key,
            plan_key,
            lifecycle_status,
            event_code,
            event_timestamp_ms,
            updated_at,
        ),
    )


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
    lifecycle_status = _EVENT_STATUS.get(event_code)
    if lifecycle_status is None:
        return {"ok": False, "created": False, "reason": "unsupported_event"}
    channel = str(remote_channel or "").strip().lower() or None
    if channel is not None and re.fullmatch(r"[a-f0-9]{64}", channel) is None:
        return {"ok": False, "created": False, "reason": "invalid_remote_channel"}
    try:
        remote_id = int(remote_event_id) if remote_event_id is not None else None
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "created": False, "reason": "invalid_remote_event_id"}
    if remote_id is not None and remote_id <= 0:
        return {"ok": False, "created": False, "reason": "invalid_remote_event_id"}

    user_id = int(tenant.user_id)
    portfolio_id = int(tenant.portfolio_id)
    symbol = _canonical_symbol(parsed.get("symbol"))
    timeframe = str(parsed.get("timeframe") or "")
    plan_key = _plan_key(parsed)
    scope_identity = _scope_identity(user_id, portfolio_id, symbol, timeframe)
    scope_key = _scope_key(user_id, portfolio_id, symbol, timeframe)
    event_key = _event_key(parsed, user_id, portfolio_id)
    event_time_ms = int(parsed["event_timestamp_ms"])
    entry, stop, target1, target2, target3 = _levels(parsed)
    geometry = parsed.get("geometry") if isinstance(parsed.get("geometry"), dict) else {}
    received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    conn = None
    kind = ""
    with _LOCAL_EVENT_LOCK:
        try:
            conn, kind = database.get_connection()
            cursor = _begin_locked_transaction(conn, kind, scope_identity)
            if _event_exists_in_transaction(cursor, kind, event_key, user_id, portfolio_id):
                conn.rollback()
                return {
                    "ok": True,
                    "created": False,
                    "reason": "duplicate",
                    "event_key": event_key,
                    "plan_key": plan_key,
                    "scope_key": scope_key,
                    "lifecycle_status": lifecycle_status,
                    "parsed": parsed,
                }
            latest = _load_state(
                cursor,
                kind,
                user_id,
                portfolio_id,
                symbol,
                timeframe,
            )
            transition_error = _validate_transition(
                event_code,
                event_time_ms,
                plan_key,
                latest,
            )
            if transition_error:
                conn.rollback()
                return {
                    "ok": False,
                    "created": False,
                    "reason": transition_error,
                    "event_key": event_key,
                    "plan_key": plan_key,
                    "scope_key": scope_key,
                    "parsed": parsed,
                }
            query = f"""
                INSERT INTO {TABLE}(
                    event_key,user_id,portfolio_id,scope_key,plan_key,source,event_code,
                    event_rank,symbol,timeframe,direction,lifecycle_status,event_time,
                    event_timestamp_ms,event_price,entry_price,stop_price,target1,target2,
                    target3,confidence,geometry_valid,payload_json,remote_event_id,
                    remote_channel,received_at
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(event_key) DO NOTHING
            """
            cursor.execute(
                _adapt(query, kind),
                (
                    event_key,
                    user_id,
                    portfolio_id,
                    scope_key,
                    plan_key,
                    parsed.get("source"),
                    event_code,
                    _EVENT_RANK[event_code],
                    symbol,
                    timeframe,
                    parsed.get("direction"),
                    lifecycle_status,
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
                    remote_id,
                    channel,
                    received_at,
                ),
            )
            created = cursor.rowcount == 1
            if not created:
                conn.rollback()
                return {
                    "ok": True,
                    "created": False,
                    "reason": "duplicate",
                    "event_key": event_key,
                    "plan_key": plan_key,
                    "scope_key": scope_key,
                    "lifecycle_status": lifecycle_status,
                    "parsed": parsed,
                }
            _upsert_state(
                cursor,
                kind,
                user_id=user_id,
                portfolio_id=portfolio_id,
                symbol=symbol,
                timeframe=timeframe,
                scope_key=scope_key,
                plan_key=plan_key,
                lifecycle_status=lifecycle_status,
                event_code=event_code,
                event_timestamp_ms=event_time_ms,
                updated_at=received_at,
            )
            conn.commit()
            return {
                "ok": True,
                "created": True,
                "reason": None,
                "event_key": event_key,
                "plan_key": plan_key,
                "scope_key": scope_key,
                "lifecycle_status": lifecycle_status,
                "parsed": parsed,
            }
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    LOGGER.exception("External journal rollback failed")
            LOGGER.exception("Atomic external event transaction failed")
            return {
                "ok": False,
                "created": False,
                "reason": "database_state_unavailable",
                "plan_key": plan_key,
                "scope_key": scope_key,
                "parsed": parsed,
            }
        finally:
            if conn is not None:
                database.put_connection(conn, kind)


def quarantine_remote_event(
    remote_channel: str,
    remote_event_id: int,
    payload: Any,
    reason: str,
) -> dict[str, Any]:
    tenant = current_tenant()
    channel = str(remote_channel or "").strip().lower()
    if tenant is None:
        return {"ok": False, "created": False, "reason": "no_active_tenant"}
    if re.fullmatch(r"[a-f0-9]{64}", channel) is None:
        return {"ok": False, "created": False, "reason": "invalid_remote_channel"}
    try:
        remote_id = int(remote_event_id)
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "created": False, "reason": "invalid_remote_event_id"}
    if remote_id <= 0:
        return {"ok": False, "created": False, "reason": "invalid_remote_event_id"}
    install_external_signal_journal()
    safe_reason = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(reason or "rejected"))[:120]
    try:
        payload_json = strict_json_dumps(payload if isinstance(payload, dict) else {"raw": str(payload)[:2000]})
    except Exception:
        payload_json = strict_json_dumps({"unserializable_payload": True})
    result = execute_write(
        f"""
        INSERT INTO {QUARANTINE_TABLE}(
            user_id,portfolio_id,remote_channel,remote_event_id,reason,payload_json,quarantined_at
        ) VALUES(%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(user_id,portfolio_id,remote_channel,remote_event_id) DO NOTHING
        """,
        (
            int(tenant.user_id),
            int(tenant.portfolio_id),
            channel,
            remote_id,
            safe_reason,
            payload_json,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )
    if not result.ok:
        return {"ok": False, "created": False, "reason": result.reason or "quarantine_write_failed"}
    return {
        "ok": True,
        "created": result.rowcount == 1,
        "reason": None if result.rowcount == 1 else "duplicate",
        "remote_event_id": remote_id,
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
    params: list[Any] = [int(tenant.user_id), int(tenant.portfolio_id)]
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
        "confidence,geometry_valid,payload_json,received_at,scope_key,plan_key,remote_event_id,remote_channel "
        f"FROM {TABLE} WHERE {' AND '.join(clauses)} "
        f"ORDER BY event_timestamp_ms DESC, received_at DESC LIMIT {safe_limit}",
        tuple(params),
    )
    return frame.reset_index(drop=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def recent_quarantined_events(*, limit: int = 50) -> pd.DataFrame:
    tenant = current_tenant()
    if tenant is None:
        return pd.DataFrame()
    install_external_signal_journal()
    safe_limit = max(1, min(500, int(limit)))
    frame = _fetch_explicit(
        f"SELECT remote_channel,remote_event_id,reason,payload_json,quarantined_at "
        f"FROM {QUARANTINE_TABLE} WHERE user_id=%s AND portfolio_id=%s "
        f"ORDER BY remote_event_id DESC LIMIT {safe_limit}",
        (int(tenant.user_id), int(tenant.portfolio_id)),
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
        return {"available": False, "events": 0, "read_error": bool(frame.attrs.get("read_error"))}
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
        "scope_key": latest.get("scope_key"),
        "plan_key": latest.get("plan_key"),
    }


def latest_remote_cursor(remote_channel: str) -> int:
    tenant = current_tenant()
    channel = str(remote_channel or "").strip().lower()
    if tenant is None or re.fullmatch(r"[a-f0-9]{64}", channel) is None:
        return 0
    install_external_signal_journal()
    frame = _fetch_explicit(
        f"SELECT MAX(cursor_value) AS cursor FROM ("
        f"SELECT MAX(remote_event_id) AS cursor_value FROM {TABLE} "
        "WHERE user_id=%s AND portfolio_id=%s AND remote_channel=%s "
        "UNION ALL "
        f"SELECT MAX(remote_event_id) AS cursor_value FROM {QUARANTINE_TABLE} "
        "WHERE user_id=%s AND portfolio_id=%s AND remote_channel=%s"
        ") AS cursor_values",
        (
            int(tenant.user_id),
            int(tenant.portfolio_id),
            channel,
            int(tenant.user_id),
            int(tenant.portfolio_id),
            channel,
        ),
    )
    if frame.empty:
        return 0
    value = pd.to_numeric(frame.iloc[0].get("cursor"), errors="coerce")
    return int(value) if pd.notna(value) and int(value) > 0 else 0


__all__ = [
    "JournalStateError",
    "QUARANTINE_TABLE",
    "STATE_TABLE",
    "TABLE",
    "install_external_signal_journal",
    "latest_external_event",
    "latest_remote_cursor",
    "lifecycle_snapshot",
    "quarantine_remote_event",
    "recent_external_events",
    "recent_quarantined_events",
    "record_external_event",
]
