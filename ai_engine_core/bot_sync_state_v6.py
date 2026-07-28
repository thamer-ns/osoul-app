"""Durable per-tenant cursors for the Osoli ↔ market-bot pull channel."""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import database
from database_write_v6 import execute_write
from tenant_scope import current_tenant

LOGGER = logging.getLogger(__name__)
TABLE = "external_bot_sync_state_v6"
_LOCK = threading.RLock()
_INSTALLED = False


def _fetch(query: str, params: tuple[Any, ...]) -> pd.DataFrame:
    conn = None
    kind = ""
    try:
        conn, kind = database.get_connection()
        adapted = database._adapt_query_for_kind(query, kind)  # noqa: SLF001
        return pd.read_sql(adapted, conn, params=params)
    except Exception:
        LOGGER.exception("Bot sync-state read failed")
        return pd.DataFrame()
    finally:
        if conn is not None:
            database.put_connection(conn, kind)


def install_sync_state() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            user_id INTEGER NOT NULL,
            portfolio_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            cursor_value BIGINT NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, portfolio_id, channel)
        )
        """
        if not database.execute_query(ddl):
            raise RuntimeError("تعذر إنشاء حالة مزامنة البوت")
        _INSTALLED = True


def _valid_channel(channel: str) -> str:
    value = str(channel or "").strip().lower()
    if re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("invalid sync channel")
    return value


def load_cursor(channel: str) -> int:
    tenant = current_tenant()
    if tenant is None:
        return 0
    install_sync_state()
    try:
        value = _valid_channel(channel)
    except ValueError:
        return 0
    frame = _fetch(
        f"SELECT cursor_value FROM {TABLE} WHERE user_id=%s AND portfolio_id=%s AND channel=%s LIMIT 1",
        (tenant.user_id, tenant.portfolio_id, value),
    )
    if frame.empty:
        return 0
    numeric = pd.to_numeric(frame.iloc[0].get("cursor_value"), errors="coerce")
    return int(numeric) if pd.notna(numeric) and int(numeric) > 0 else 0


def save_cursor(channel: str, cursor: int) -> bool:
    tenant = current_tenant()
    if tenant is None or int(cursor) < 0:
        return False
    install_sync_state()
    try:
        value = _valid_channel(channel)
    except ValueError:
        return False
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    query = f"""
    INSERT INTO {TABLE} (user_id, portfolio_id, channel, cursor_value, updated_at)
    VALUES (%s,%s,%s,%s,%s)
    ON CONFLICT (user_id, portfolio_id, channel) DO UPDATE SET
        cursor_value=CASE
            WHEN excluded.cursor_value > {TABLE}.cursor_value THEN excluded.cursor_value
            ELSE {TABLE}.cursor_value
        END,
        updated_at=excluded.updated_at
    """
    result = execute_write(
        query,
        (tenant.user_id, tenant.portfolio_id, value, int(cursor), now),
    )
    return bool(result.ok)


__all__ = ["install_sync_state", "load_cursor", "save_cursor"]
