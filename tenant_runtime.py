"""Runtime compatibility guards for legacy Osoli modules.

Legacy pages import ``database.fetch_table`` directly. Installing this guard
before the lazy page imports transparently scopes personal tables to the
authenticated user and maps globally-unique legacy watchlist/thesis tables to
safe v2 tables.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

import database
from database import fetch_df, get_connection, put_connection
from tenant_db import current_username, fetch_user_table

_ORIGINAL_FETCH_TABLE = database.fetch_table
_INSTALLED = False
_PERSONAL_TABLES = {
    "trades",
    "deposits",
    "withdrawals",
    "returnsgrants",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _execute(pg_sql: str, sqlite_sql: str | None = None, params: tuple[Any, ...] = ()) -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(pg_sql if kind == "postgres" else (sqlite_sql or pg_sql.replace("%s", "?")), params)
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


def ensure_personal_v2_tables() -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, symbol)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS investment_theses_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    thesis_text TEXT,
                    target_price NUMERIC(20,6),
                    recommendation TEXT,
                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, symbol)
                )
                """
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, symbol)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS investment_theses_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    thesis_text TEXT,
                    target_price REAL,
                    recommendation TEXT,
                    last_updated TEXT NOT NULL,
                    UNIQUE(user_id, symbol)
                )
                """
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        put_connection(conn, kind)

    _migrate_single_user_personal_rows()
    return True


def _single_username() -> str:
    try:
        users = _ORIGINAL_FETCH_TABLE("users")
        if users is None or users.empty or "username" not in users.columns:
            return ""
        names = list(dict.fromkeys(str(x).strip() for x in users["username"].dropna() if str(x).strip()))
        return names[0] if len(names) == 1 else ""
    except Exception:
        return ""


def _migrate_single_user_personal_rows() -> None:
    username = _single_username()
    if not username:
        return
    try:
        legacy_watch = _ORIGINAL_FETCH_TABLE("watchlist")
        if legacy_watch is not None and not legacy_watch.empty and "symbol" in legacy_watch.columns:
            for symbol in legacy_watch["symbol"].dropna().astype(str):
                add_watch_symbol(symbol, username=username)
    except Exception:
        pass
    try:
        legacy_thesis = _ORIGINAL_FETCH_TABLE("investmentthesis")
        if legacy_thesis is not None and not legacy_thesis.empty and "symbol" in legacy_thesis.columns:
            for _, row in legacy_thesis.iterrows():
                save_thesis_v2(
                    row.get("symbol"),
                    row.get("thesis_text", ""),
                    row.get("target_price", 0),
                    row.get("recommendation", "Hold"),
                    username=username,
                )
    except Exception:
        pass


def fetch_watchlist(username: str = "") -> pd.DataFrame:
    username = str(username or current_username()).strip()
    return fetch_df(
        "SELECT id,user_id,symbol,created_at FROM watchlist_v2 WHERE user_id=%s ORDER BY symbol",
        (username,),
    )


def add_watch_symbol(symbol: str, username: str = "") -> bool:
    username = str(username or current_username()).strip()
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return False
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                INSERT INTO watchlist_v2 (user_id,symbol,created_at)
                VALUES (%s,%s,%s)
                ON CONFLICT (user_id,symbol) DO NOTHING
                """,
                (username, symbol, _now()),
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO watchlist_v2 (user_id,symbol,created_at) VALUES (?,?,?)",
                (username, symbol, _now()),
            )
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


def remove_watch_symbol(symbol: str, username: str = "") -> bool:
    username = str(username or current_username()).strip()
    return _execute(
        "DELETE FROM watchlist_v2 WHERE user_id=%s AND symbol=%s",
        params=(username, str(symbol or "").strip().upper()),
    )


def get_thesis_v2(symbol: str, username: str = ""):
    username = str(username or current_username()).strip()
    frame = fetch_df(
        "SELECT * FROM investment_theses_v2 WHERE user_id=%s AND symbol=%s LIMIT 1",
        (username, str(symbol or "").strip().upper()),
    )
    return None if frame is None or frame.empty else frame.iloc[0]


def save_thesis_v2(
    symbol: str,
    thesis_text: str,
    target_price: Any,
    recommendation: str,
    username: str = "",
) -> bool:
    username = str(username or current_username()).strip()
    symbol = str(symbol or "").strip().upper()
    try:
        target = float(target_price or 0.0)
    except Exception:
        target = 0.0
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                INSERT INTO investment_theses_v2
                    (user_id,symbol,thesis_text,target_price,recommendation,last_updated)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (user_id,symbol) DO UPDATE SET
                    thesis_text=EXCLUDED.thesis_text,
                    target_price=EXCLUDED.target_price,
                    recommendation=EXCLUDED.recommendation,
                    last_updated=EXCLUDED.last_updated
                """,
                (username, symbol, str(thesis_text or ""), target, str(recommendation or "Hold")[:20], _now()),
            )
        else:
            cur.execute(
                """
                INSERT INTO investment_theses_v2
                    (user_id,symbol,thesis_text,target_price,recommendation,last_updated)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id,symbol) DO UPDATE SET
                    thesis_text=excluded.thesis_text,
                    target_price=excluded.target_price,
                    recommendation=excluded.recommendation,
                    last_updated=excluded.last_updated
                """,
                (username, symbol, str(thesis_text or ""), target, str(recommendation or "Hold")[:20], _now()),
            )
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


def _scoped_fetch_table(table: str) -> pd.DataFrame:
    key = str(table or "").strip().lower()
    try:
        username = current_username(required=False)
    except Exception:
        username = ""
    if not username:
        return _ORIGINAL_FETCH_TABLE(table)
    if key in _PERSONAL_TABLES:
        return fetch_user_table(key, username)
    if key == "watchlist":
        return fetch_watchlist(username)
    if key in {"investmentthesis", "investment_theses_v2"}:
        return fetch_df("SELECT * FROM investment_theses_v2 WHERE user_id=%s", (username,))
    return _ORIGINAL_FETCH_TABLE(table)


def install_runtime_guards() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True
    if not ensure_personal_v2_tables():
        return False
    database.fetch_table = _scoped_fetch_table
    _INSTALLED = True
    return True
