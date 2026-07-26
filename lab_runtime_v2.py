"""Tenant guards for backtest/lab history."""
from __future__ import annotations

from typing import Any

import pandas as pd

import database
from database import fetch_df, get_connection, put_connection
from tenant_db import current_username

_INSTALLED = False
_LAB_TABLES = {"lab_runs", "lab_trades", "lab_equity", "ai_decisions"}
_PREVIOUS_FETCH = None


def _column_exists(table: str, column: str) -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s
                LIMIT 1
                """,
                (table, column),
            )
            return cur.fetchone() is not None
        cur.execute(f"PRAGMA table_info({table})")
        return any(str(row[1]).lower() == column.lower() for row in (cur.fetchall() or []))
    finally:
        put_connection(conn, kind)


def _ensure_user_columns() -> bool:
    try:
        import backtester

        backtester.ensure_lab_tables()
    except Exception:
        pass
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        for table in _LAB_TABLES:
            if _column_exists(table, "user_id"):
                continue
            cur.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        put_connection(conn, kind)
    _backfill_single_user()
    return True


def _backfill_single_user() -> None:
    try:
        users = (_PREVIOUS_FETCH or database.fetch_table)("users")
        if users is None or users.empty or "username" not in users.columns:
            return
        names = list(dict.fromkeys(str(x).strip() for x in users["username"].dropna() if str(x).strip()))
        if len(names) != 1:
            return
        username = names[0]
    except Exception:
        return
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        placeholder = "%s" if kind == "postgres" else "?"
        for table in _LAB_TABLES:
            cur.execute(
                f"UPDATE {table} SET user_id={placeholder} WHERE user_id IS NULL OR TRIM(user_id)=''",
                (username,),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        put_connection(conn, kind)


def _scoped_lab_fetch(table: str) -> pd.DataFrame:
    key = str(table or "").strip().lower()
    username = current_username(required=False)
    if username and key in _LAB_TABLES:
        return fetch_df(f"SELECT * FROM {key} WHERE user_id=%s", (username,))
    return _PREVIOUS_FETCH(table)


def _mark_run_owner(run_id: str, username: str) -> None:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        placeholder = "%s" if kind == "postgres" else "?"
        for table in ("lab_runs", "lab_trades", "lab_equity"):
            cur.execute(
                f"UPDATE {table} SET user_id={placeholder} WHERE run_id={placeholder}",
                (username, run_id),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        put_connection(conn, kind)


def _scoped_link_decision(symbol: str, sector: str, run_id: str, outcome_return_pct: float):
    del sector
    username = current_username(required=False)
    if not username or not symbol:
        return
    decisions = fetch_df(
        """
        SELECT * FROM ai_decisions
        WHERE user_id=%s AND symbol=%s
          AND (linked_run_id IS NULL OR linked_run_id='')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (username, str(symbol)),
    )
    if decisions is None or decisions.empty or "decision_id" not in decisions.columns:
        return
    decision_id = str(decisions.iloc[0]["decision_id"])
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                UPDATE ai_decisions
                SET linked_run_id=%s,outcome_return_pct=%s,outcome_notes=%s
                WHERE decision_id=%s AND user_id=%s
                """,
                (run_id, float(outcome_return_pct), "Linked with latest lab run", decision_id, username),
            )
        else:
            cur.execute(
                """
                UPDATE ai_decisions
                SET linked_run_id=?,outcome_return_pct=?,outcome_notes=?
                WHERE decision_id=? AND user_id=?
                """,
                (run_id, float(outcome_return_pct), "Linked with latest lab run", decision_id, username),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        put_connection(conn, kind)


def install_lab_runtime_guards() -> bool:
    global _INSTALLED, _PREVIOUS_FETCH
    if _INSTALLED:
        return True
    _PREVIOUS_FETCH = database.fetch_table
    if not _ensure_user_columns():
        return False
    database.fetch_table = _scoped_lab_fetch

    import backtester

    # backtester imported fetch_table by value before this guard was installed.
    # Replace that local reference as well, otherwise lab history reads remain global.
    backtester.fetch_table = _scoped_lab_fetch
    original_persist = backtester._persist_run_to_db

    def persist_scoped(*args: Any, **kwargs: Any):
        result = original_persist(*args, **kwargs)
        run_id = kwargs.get("run_id") or (args[0] if args else "")
        username = current_username(required=False)
        if run_id and username:
            _mark_run_owner(str(run_id), username)
        return result

    backtester._persist_run_to_db = persist_scoped
    backtester._link_latest_ai_decision_to_run = _scoped_link_decision
    _INSTALLED = True
    return True
