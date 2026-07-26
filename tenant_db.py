"""User-scoped database access for Osoli.

This module upgrades the legacy single-tenant schema in-place without deleting
existing data. Every portfolio write is scoped by ``user_id`` and every read
filters by the authenticated user.

Legacy rows are backfilled only when the database contains exactly one user.
When multiple users already exist, unowned rows remain hidden until an
administrator assigns them explicitly.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import pandas as pd
import streamlit as st

from database import fetch_df, get_connection, put_connection

_CORE_TABLES = (
    "trades",
    "deposits",
    "withdrawals",
    "returnsgrants",
    "watchlist",
    "investmentthesis",
)
_SAFE_TABLES = set(_CORE_TABLES) | {"users"}
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def current_username(required: bool = True) -> str:
    username = str(st.session_state.get("username") or "").strip()
    if required and not username:
        raise RuntimeError("لا توجد جلسة مستخدم صالحة.")
    return username


def _ident(name: str) -> str:
    value = str(name or "").strip().lower()
    if value not in _SAFE_TABLES or not _SAFE_IDENT.fullmatch(value):
        raise ValueError(f"اسم جدول غير مسموح: {name}")
    return value


def _execute_raw(query_pg: str, query_sqlite: Optional[str] = None, params: Iterable[Any] = ()) -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        query = query_pg if kind == "postgres" else (query_sqlite or query_pg.replace("%s", "?"))
        cur.execute(query, tuple(params))
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        put_connection(conn, kind)


def _column_exists(table: str, column: str) -> bool:
    table = _ident(table)
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            )
        else:
            cur.execute(f"PRAGMA table_info({table})")
            return any(str(row[1]).lower() == column.lower() for row in (cur.fetchall() or []))
        return cur.fetchone() is not None
    finally:
        put_connection(conn, kind)


def _add_column(table: str, column: str, pg_type: str, sqlite_type: str) -> None:
    if _column_exists(table, column):
        return
    table = _ident(table)
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        col_type = pg_type if kind == "postgres" else sqlite_type
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        put_connection(conn, kind)


def _table_exists(table: str) -> bool:
    table = _ident(table)
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name=%s LIMIT 1",
                (table,),
            )
        else:
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,))
        return cur.fetchone() is not None
    finally:
        put_connection(conn, kind)


def _backfill_single_user_legacy_rows() -> None:
    try:
        users = fetch_df("SELECT username FROM users ORDER BY id")
    except Exception:
        return
    if users is None or users.empty or "username" not in users.columns:
        return
    names = [str(x).strip() for x in users["username"].dropna().tolist() if str(x).strip()]
    names = list(dict.fromkeys(names))
    if len(names) != 1:
        return
    username = names[0]
    for table in _CORE_TABLES:
        if not _table_exists(table) or not _column_exists(table, "user_id"):
            continue
        _execute_raw(
            f"UPDATE {table} SET user_id=%s WHERE user_id IS NULL OR TRIM(user_id)=''",
            params=(username,),
        )


@st.cache_resource(show_spinner=False)
def ensure_tenant_schema() -> bool:
    """Upgrade legacy portfolio tables to user-scoped storage."""
    for table in _CORE_TABLES:
        if _table_exists(table):
            _add_column(table, "user_id", "TEXT", "TEXT")

    if _table_exists("trades"):
        for name in ("entry_fees", "exit_fees"):
            _add_column("trades", name, "NUMERIC(20,6) DEFAULT 0", "REAL DEFAULT 0")
        _add_column("trades", "notes", "TEXT", "TEXT")

    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        for table in _CORE_TABLES:
            if not _table_exists(table):
                continue
            try:
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")
            except Exception:
                pass
        try:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    details TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
                if kind == "postgres"
                else """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    details TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        except Exception:
            pass
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        put_connection(conn, kind)

    _backfill_single_user_legacy_rows()
    return True


def fetch_user_table(table: str, username: Optional[str] = None) -> pd.DataFrame:
    ensure_tenant_schema()
    table = _ident(table)
    username = str(username or current_username()).strip()
    if not _column_exists(table, "user_id"):
        return pd.DataFrame()
    return fetch_df(f"SELECT * FROM {table} WHERE user_id=%s", (username,))


def _audit(username: str, action: str, entity_type: str, entity_id: Any = None, details: str = "") -> None:
    try:
        _execute_raw(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, details, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            params=(username, action, entity_type, str(entity_id or ""), details[:2000], _now_iso()),
        )
    except Exception:
        pass


def insert_trade(
    *,
    symbol: str,
    company_name: str,
    sector: str,
    asset_type: str,
    quantity: float,
    entry_price: float,
    strategy: str,
    trade_date: str,
    entry_fees: float = 0.0,
    notes: str = "",
    username: Optional[str] = None,
) -> bool:
    ensure_tenant_schema()
    username = str(username or current_username()).strip()
    ok = _execute_raw(
        """
        INSERT INTO trades (
            user_id, symbol, company_name, sector, asset_type, quantity,
            entry_price, current_price, entry_fees, exit_fees, strategy,
            status, date, notes, created_at, updated_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,'Open',%s,%s,%s,%s)
        """,
        params=(
            username,
            symbol,
            company_name,
            sector,
            asset_type,
            float(quantity),
            float(entry_price),
            float(entry_price),
            float(entry_fees or 0.0),
            strategy,
            trade_date,
            notes,
            _now_iso(),
            _now_iso(),
        ),
    )
    if ok:
        _audit(username, "insert", "trade", details=f"{symbol}|{quantity}|{entry_price}")
    return ok


def close_trade(
    trade_id: Any,
    *,
    exit_price: float,
    exit_date: str,
    exit_fees: float = 0.0,
    username: Optional[str] = None,
) -> bool:
    username = str(username or current_username()).strip()
    ok = _execute_raw(
        """
        UPDATE trades
        SET status='Close', exit_price=%s, current_price=%s, exit_date=%s,
            exit_fees=%s, updated_at=%s
        WHERE id=%s AND user_id=%s
        """,
        params=(
            float(exit_price),
            float(exit_price),
            exit_date,
            float(exit_fees or 0.0),
            _now_iso(),
            trade_id,
            username,
        ),
    )
    if ok:
        _audit(username, "close", "trade", trade_id, f"exit={exit_price}")
    return ok


def update_trade(
    trade_id: Any,
    *,
    quantity: float,
    entry_price: float,
    trade_date: str,
    entry_fees: float = 0.0,
    exit_price: Optional[float] = None,
    exit_date: Optional[str] = None,
    exit_fees: float = 0.0,
    notes: str = "",
    username: Optional[str] = None,
) -> bool:
    username = str(username or current_username()).strip()
    if exit_price is None:
        ok = _execute_raw(
            """
            UPDATE trades
            SET quantity=%s, entry_price=%s, date=%s, entry_fees=%s,
                notes=%s, updated_at=%s
            WHERE id=%s AND user_id=%s
            """,
            params=(
                float(quantity),
                float(entry_price),
                trade_date,
                float(entry_fees or 0.0),
                notes,
                _now_iso(),
                trade_id,
                username,
            ),
        )
    else:
        ok = _execute_raw(
            """
            UPDATE trades
            SET quantity=%s, entry_price=%s, date=%s, entry_fees=%s,
                exit_price=%s, current_price=%s, exit_date=%s, exit_fees=%s,
                notes=%s, updated_at=%s
            WHERE id=%s AND user_id=%s
            """,
            params=(
                float(quantity),
                float(entry_price),
                trade_date,
                float(entry_fees or 0.0),
                float(exit_price),
                float(exit_price),
                exit_date,
                float(exit_fees or 0.0),
                notes,
                _now_iso(),
                trade_id,
                username,
            ),
        )
    if ok:
        _audit(username, "update", "trade", trade_id)
    return ok


def insert_cash_transaction(
    table: str,
    *,
    amount: float,
    tx_date: str,
    note: str = "",
    symbol: str = "",
    username: Optional[str] = None,
) -> bool:
    table = _ident(table)
    if table not in {"deposits", "withdrawals", "returnsgrants"}:
        raise ValueError("نوع حركة نقدية غير مسموح")
    username = str(username or current_username()).strip()
    if table == "returnsgrants":
        ok = _execute_raw(
            f"INSERT INTO {table} (user_id,date,symbol,amount,note,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            params=(username, tx_date, symbol, float(amount), note, _now_iso()),
        )
    else:
        ok = _execute_raw(
            f"INSERT INTO {table} (user_id,date,amount,note,created_at) "
            "VALUES (%s,%s,%s,%s,%s)",
            params=(username, tx_date, float(amount), note, _now_iso()),
        )
    if ok:
        _audit(username, "insert", table, details=f"{amount}")
    return ok


def update_cash_transaction(
    table: str,
    tx_id: Any,
    *,
    amount: float,
    tx_date: str,
    note: str = "",
    symbol: str = "",
    username: Optional[str] = None,
) -> bool:
    table = _ident(table)
    if table not in {"deposits", "withdrawals", "returnsgrants"}:
        raise ValueError("نوع حركة نقدية غير مسموح")
    username = str(username or current_username()).strip()
    if table == "returnsgrants":
        ok = _execute_raw(
            f"UPDATE {table} SET amount=%s,date=%s,note=%s,symbol=%s "
            "WHERE id=%s AND user_id=%s",
            params=(float(amount), tx_date, note, symbol, tx_id, username),
        )
    else:
        ok = _execute_raw(
            f"UPDATE {table} SET amount=%s,date=%s,note=%s "
            "WHERE id=%s AND user_id=%s",
            params=(float(amount), tx_date, note, tx_id, username),
        )
    if ok:
        _audit(username, "update", table, tx_id)
    return ok


def update_open_price(symbol: str, price: float, username: Optional[str] = None) -> bool:
    username = str(username or current_username()).strip()
    return _execute_raw(
        """
        UPDATE trades
        SET current_price=%s, updated_at=%s
        WHERE symbol=%s AND LOWER(status)='open' AND user_id=%s
        """,
        params=(float(price), _now_iso(), symbol, username),
    )
