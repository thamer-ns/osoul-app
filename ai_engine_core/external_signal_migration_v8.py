"""Idempotent tenant-by-tenant migration from the V6 SC journal to V7.

The V7 tables became authoritative for lifecycle reads. Existing V6 events must
therefore be copied before the next T1/SL/C event is validated, otherwise an
active plan looks as though its initial NL/NS never existed. This module runs
only for the authenticated tenant, preserves event identities, recomputes V7
plan identities, and rebuilds state from the newest V7 row after the copy.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

import database
from ai_engine_core.compass_contract import normalise_timeframe
from tenant_scope import current_tenant

from . import external_signal_journal_v7 as journal

LOGGER = logging.getLogger(__name__)
LEGACY_TABLE = "external_analysis_events_v6"
MIGRATION_TABLE = "external_signal_migrations_v8"
MIGRATION_NAME = "external_events_v6_to_v7"
_LOCK = threading.RLock()
_DONE: set[tuple[int, int]] = set()


def _adapt(query: str, kind: str) -> str:
    return database._adapt_query_for_kind(query, kind)  # noqa: SLF001


def _row(cursor: Any, raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if hasattr(raw, "keys"):
        return {str(key): raw[key] for key in raw.keys()}
    columns = [str(item[0]) for item in (cursor.description or [])]
    return dict(zip(columns, raw, strict=False))


def _table_exists(cursor: Any, kind: str, table: str) -> bool:
    if kind == "sqlite":
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        )
    else:
        cursor.execute("SELECT to_regclass(%s)", (table,))
    raw = cursor.fetchone()
    if raw is None:
        return False
    value = raw[0] if not hasattr(raw, "keys") else next(iter(raw.values()))
    return bool(value)


def _ensure_marker_table() -> None:
    import tenant_scope

    tenant_scope.SCOPED_TABLES.add(MIGRATION_TABLE)
    if not database.execute_query(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            user_id INTEGER NOT NULL,
            portfolio_id INTEGER NOT NULL,
            migration_name TEXT NOT NULL,
            migrated_rows INTEGER NOT NULL DEFAULT 0,
            migrated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, portfolio_id, migration_name)
        )
        """
    ):
        raise RuntimeError("تعذر إنشاء سجل ترحيل أحداث المؤشر")


def _marker_exists(
    cursor: Any,
    kind: str,
    user_id: int,
    portfolio_id: int,
) -> bool:
    cursor.execute(
        _adapt(
            f"SELECT 1 FROM {MIGRATION_TABLE} "
            "WHERE user_id=%s AND portfolio_id=%s AND migration_name=%s LIMIT 1",
            kind,
        ),
        (user_id, portfolio_id, MIGRATION_NAME),
    )
    return cursor.fetchone() is not None


def _direction_identity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "buy", "long", "bull", "bullish"}:
        return "buy"
    if text in {"-1", "sell", "short", "bear", "bearish"}:
        return "sell"
    return text or "neutral"


def _v7_plan_key(item: dict[str, Any], symbol: str, timeframe: str) -> str:
    """Rebuild plan identity using V7's canonical numeric formatting.

    V6 used ``str(float)`` while V7 uses ``.12g``. Preserving a V6 hash would
    reject a later T1/SL/C for integer-valued levels such as ``100.0`` because
    V7 correctly identifies the same value as ``100``.
    """
    targets = [item.get("target1"), item.get("target2"), item.get("target3")]
    return journal._plan_key(  # noqa: SLF001
        {
            "source": str(item.get("source") or ""),
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": _direction_identity(item.get("direction")),
            "entry": item.get("entry_price"),
            "stop": item.get("stop_price"),
            "targets": targets,
        }
    )


def migrate_current_tenant_v6_to_v7() -> dict[str, Any]:
    """Copy legacy rows and rebuild V7 state for the authenticated tenant."""
    tenant = current_tenant()
    if tenant is None:
        return {"ok": False, "reason": "no_active_tenant", "migrated": 0}
    key = (int(tenant.user_id), int(tenant.portfolio_id))
    with _LOCK:
        if key in _DONE:
            return {"ok": True, "reason": "already_checked", "migrated": 0}

        journal.install_external_signal_journal()
        _ensure_marker_table()
        conn = None
        kind = ""
        try:
            conn, kind = database.get_connection()
            cursor = conn.cursor()
            if kind == "sqlite":
                cursor.execute("BEGIN IMMEDIATE")
            else:
                try:
                    conn.autocommit = False
                except Exception:
                    LOGGER.debug("Unable to disable autocommit for migration", exc_info=True)

            if _marker_exists(cursor, kind, *key):
                conn.commit()
                _DONE.add(key)
                return {"ok": True, "reason": "already_migrated", "migrated": 0}
            if not _table_exists(cursor, kind, LEGACY_TABLE):
                conn.commit()
                _DONE.add(key)
                return {"ok": True, "reason": "legacy_table_absent", "migrated": 0}

            cursor.execute(
                _adapt(
                    f"SELECT event_key,plan_key,source,event_code,event_rank,symbol,"
                    "timeframe,direction,lifecycle_status,event_time,event_timestamp_ms,"
                    "event_price,entry_price,stop_price,target1,target2,target3,confidence,"
                    "geometry_valid,payload_json,remote_event_id,remote_channel,received_at "
                    f"FROM {LEGACY_TABLE} WHERE user_id=%s AND portfolio_id=%s "
                    "ORDER BY event_timestamp_ms ASC, received_at ASC",
                    kind,
                ),
                key,
            )
            rows: list[dict[str, Any]] = []
            while True:
                item = _row(cursor, cursor.fetchone())
                if item is None:
                    break
                rows.append(item)

            affected: set[tuple[str, str]] = set()
            inserted = 0
            insert_query = _adapt(
                f"""
                INSERT INTO {journal.TABLE}(
                    event_key,user_id,portfolio_id,scope_key,plan_key,source,event_code,
                    event_rank,symbol,timeframe,direction,lifecycle_status,event_time,
                    event_timestamp_ms,event_price,entry_price,stop_price,target1,target2,
                    target3,confidence,geometry_valid,payload_json,remote_event_id,
                    remote_channel,received_at
                ) VALUES(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s
                ) ON CONFLICT (event_key) DO NOTHING
                """,
                kind,
            )
            for item in rows:
                symbol = journal._canonical_symbol(item.get("symbol"))  # noqa: SLF001
                timeframe = normalise_timeframe(item.get("timeframe"))
                scope_key = journal._scope_key(*key, symbol, timeframe)  # noqa: SLF001
                plan_key = _v7_plan_key(item, symbol, timeframe)
                cursor.execute(
                    insert_query,
                    (
                        item.get("event_key"),
                        key[0],
                        key[1],
                        scope_key,
                        plan_key,
                        item.get("source"),
                        item.get("event_code"),
                        int(item.get("event_rank") or 0),
                        symbol,
                        timeframe,
                        _direction_identity(item.get("direction")),
                        item.get("lifecycle_status"),
                        item.get("event_time"),
                        int(item.get("event_timestamp_ms") or 0),
                        float(item.get("event_price") or 0.0),
                        item.get("entry_price"),
                        item.get("stop_price"),
                        item.get("target1"),
                        item.get("target2"),
                        item.get("target3"),
                        item.get("confidence"),
                        int(item.get("geometry_valid") or 0),
                        item.get("payload_json") or "{}",
                        item.get("remote_event_id"),
                        item.get("remote_channel"),
                        item.get("received_at")
                        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    ),
                )
                inserted += max(0, int(cursor.rowcount or 0))
                affected.add((symbol, timeframe))

            for symbol, timeframe in affected:
                cursor.execute(
                    _adapt(
                        f"SELECT plan_key,lifecycle_status,event_code,event_timestamp_ms,event_time "
                        f"FROM {journal.TABLE} WHERE user_id=%s AND portfolio_id=%s "
                        "AND symbol=%s AND timeframe=%s "
                        "ORDER BY event_timestamp_ms DESC, received_at DESC LIMIT 1",
                        kind,
                    ),
                    (*key, symbol, timeframe),
                )
                latest = _row(cursor, cursor.fetchone())
                if latest is None:
                    continue
                journal._upsert_state(  # noqa: SLF001
                    cursor,
                    kind,
                    user_id=key[0],
                    portfolio_id=key[1],
                    symbol=symbol,
                    timeframe=timeframe,
                    scope_key=journal._scope_key(*key, symbol, timeframe),  # noqa: SLF001
                    plan_key=str(latest.get("plan_key") or ""),
                    lifecycle_status=str(latest.get("lifecycle_status") or ""),
                    event_code=str(latest.get("event_code") or ""),
                    event_timestamp_ms=int(latest.get("event_timestamp_ms") or 0),
                    updated_at=str(latest.get("event_time") or ""),
                )

            migrated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            cursor.execute(
                _adapt(
                    f"INSERT INTO {MIGRATION_TABLE}(user_id,portfolio_id,migration_name,migrated_rows,migrated_at) "
                    "VALUES(%s,%s,%s,%s,%s) "
                    "ON CONFLICT(user_id,portfolio_id,migration_name) DO NOTHING",
                    kind,
                ),
                (*key, MIGRATION_NAME, inserted, migrated_at),
            )
            conn.commit()
            _DONE.add(key)
            return {"ok": True, "reason": "migrated", "migrated": inserted}
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    LOGGER.debug("Migration rollback failed", exc_info=True)
            LOGGER.exception("V6 external journal migration failed for tenant")
            return {"ok": False, "reason": "migration_failed", "migrated": 0}
        finally:
            if conn is not None:
                database.put_connection(conn, kind)


__all__ = [
    "LEGACY_TABLE",
    "MIGRATION_NAME",
    "MIGRATION_TABLE",
    "_v7_plan_key",
    "migrate_current_tenant_v6_to_v7",
]
