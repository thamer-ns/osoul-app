"""Per-user database scoping for Osoli.

This module adds non-destructive ``user_id`` / ``portfolio_id`` columns to the
legacy portfolio tables, creates a default portfolio for the signed-in user,
and installs compatibility wrappers around ``database.fetch_table``,
``database.fetch_df`` and ``database.execute_query``.

The wrappers let the existing Streamlit pages keep their public API while every
portfolio read/write is restricted to the active user. Legacy rows are claimed
only when the database contains a single user (or when the operator explicitly
sets ``OSOUL_CLAIM_LEGACY_DATA=1``).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import streamlit as st

import database as _db

SCOPED_TABLES = {
    "trades",
    "deposits",
    "withdrawals",
    "returnsgrants",
    "watchlist",
    "investmentthesis",
}

_ORIGINAL_FETCH_TABLE = _db.fetch_table
_ORIGINAL_FETCH_DF = getattr(_db, "fetch_df", None)
_ORIGINAL_EXECUTE_QUERY = _db.execute_query
_INSTALLED = False
_CONTEXT: Optional["TenantContext"] = None


@dataclass(frozen=True)
class TenantContext:
    user_id: int
    username: str
    portfolio_id: int


def _safe_ident(name: str) -> str:
    value = str(name or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("invalid SQL identifier")
    return value


def _connection_kind() -> str:
    conn, kind = _db.get_connection()
    try:
        return str(kind or "")
    finally:
        _db.put_connection(conn, kind)


def _table_columns(table: str) -> set[str]:
    table = _safe_ident(table)
    conn, kind = _db.get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s",
                (table.lower(),),
            )
            return {str(row[0]).lower() for row in (cur.fetchall() or [])}
        cur.execute(f"PRAGMA table_info({table})")
        return {str(row[1]).lower() for row in (cur.fetchall() or [])}
    finally:
        _db.put_connection(conn, kind)


def _table_exists(table: str) -> bool:
    try:
        return bool(_db.table_exists(table))
    except Exception:
        return False


def _add_column_if_missing(table: str, column: str, sql_type: str = "INTEGER") -> None:
    if not _table_exists(table):
        return
    if column.lower() in _table_columns(table):
        return
    kind = _connection_kind()
    if kind == "postgres":
        _ORIGINAL_EXECUTE_QUERY(
            f"ALTER TABLE {_safe_ident(table)} ADD COLUMN IF NOT EXISTS {_safe_ident(column)} {sql_type}"
        )
    else:
        _ORIGINAL_EXECUTE_QUERY(
            f"ALTER TABLE {_safe_ident(table)} ADD COLUMN {_safe_ident(column)} {sql_type}"
        )


def _ensure_portfolios_table() -> None:
    kind = _connection_kind()
    if kind == "postgres":
        sql = """
        CREATE TABLE IF NOT EXISTS portfolios (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            base_currency TEXT NOT NULL DEFAULT 'SAR',
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
        """
    else:
        sql = """
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            base_currency TEXT NOT NULL DEFAULT 'SAR',
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
        """
    if not _ORIGINAL_EXECUTE_QUERY(sql):
        raise RuntimeError("تعذر إنشاء جدول المحافظ")
    _ORIGINAL_EXECUTE_QUERY(
        "CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id)"
    )


def _resolve_user_id(username: str) -> int:
    df = _ORIGINAL_FETCH_DF(
        "SELECT id FROM users WHERE username=%s LIMIT 1", (str(username),)
    )
    if df is None or df.empty:
        raise RuntimeError("تعذر تحديد المستخدم الحالي")
    return int(df.iloc[0]["id"])


def _ensure_default_portfolio(user_id: int) -> int:
    df = _ORIGINAL_FETCH_DF(
        "SELECT id FROM portfolios WHERE user_id=%s ORDER BY is_default DESC, id ASC LIMIT 1",
        (int(user_id),),
    )
    if df is not None and not df.empty:
        return int(df.iloc[0]["id"])

    ok = _ORIGINAL_EXECUTE_QUERY(
        "INSERT INTO portfolios (user_id, name, base_currency, is_default) VALUES (%s,%s,%s,%s)",
        (int(user_id), "المحفظة الرئيسية", "SAR", 1),
    )
    if not ok:
        raise RuntimeError("تعذر إنشاء المحفظة الافتراضية")
    df = _ORIGINAL_FETCH_DF(
        "SELECT id FROM portfolios WHERE user_id=%s ORDER BY id DESC LIMIT 1",
        (int(user_id),),
    )
    if df is None or df.empty:
        raise RuntimeError("تعذر قراءة المحفظة الافتراضية")
    return int(df.iloc[0]["id"])


def _ensure_scoped_columns() -> None:
    for table in SCOPED_TABLES:
        if not _table_exists(table):
            continue
        _add_column_if_missing(table, "user_id", "INTEGER")
        _add_column_if_missing(table, "portfolio_id", "INTEGER")
        _ORIGINAL_EXECUTE_QUERY(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(user_id, portfolio_id)"
        )


def _claim_legacy_rows(ctx: TenantContext) -> None:
    users = _ORIGINAL_FETCH_DF("SELECT COUNT(*) AS n FROM users")
    count = int(users.iloc[0]["n"]) if users is not None and not users.empty else 0
    force = os.getenv("OSOUL_CLAIM_LEGACY_DATA", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if count > 1 and not force:
        st.session_state["_tenant_unclaimed_legacy"] = True
        return

    for table in SCOPED_TABLES:
        if not _table_exists(table):
            continue
        cols = _table_columns(table)
        if {"user_id", "portfolio_id"}.issubset(cols):
            _ORIGINAL_EXECUTE_QUERY(
                f"UPDATE {table} SET user_id=%s, portfolio_id=%s "
                "WHERE user_id IS NULL OR portfolio_id IS NULL",
                (ctx.user_id, ctx.portfolio_id),
            )


def _normalise_table(name: str) -> str:
    return str(name or "").strip().strip('"').split(".")[-1].lower()


def _extract_write_table(query: str) -> Optional[str]:
    q = str(query or "")
    patterns = [
        r"^\s*INSERT(?:\s+OR\s+REPLACE)?\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*UPDATE\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*DELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return _normalise_table(match.group(1))
    return None


def _append_scope_predicate(query: str, params: Tuple[Any, ...], ctx: TenantContext):
    q = str(query or "").strip()
    semicolon = q.endswith(";")
    if semicolon:
        q = q[:-1].rstrip()

    suffix = ""
    match = re.search(r"\s+(RETURNING|ORDER\s+BY|LIMIT)\s+", q, flags=re.IGNORECASE)
    if match:
        suffix = q[match.start():]
        q = q[:match.start()].rstrip()

    predicate = "user_id=%s AND portfolio_id=%s"
    if re.search(r"\bWHERE\b", q, flags=re.IGNORECASE):
        q = f"{q} AND {predicate}"
    else:
        q = f"{q} WHERE {predicate}"
    q = f"{q}{suffix}{';' if semicolon else ''}"
    return q, tuple(params or ()) + (ctx.user_id, ctx.portfolio_id)


def _scope_insert(query: str, params: Tuple[Any, ...], ctx: TenantContext):
    q = str(query or "")
    match = re.match(
        r"^(\s*INSERT(?:\s+OR\s+REPLACE)?\s+INTO\s+[A-Za-z_][A-Za-z0-9_]*\s*\()([^)]*)(\)\s*VALUES\s*\()([^)]*)(\).*)$",
        q,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError("صيغة INSERT غير مدعومة للجدول المعزول")
    columns = [c.strip().strip('"').lower() for c in match.group(2).split(",")]
    if "user_id" in columns or "portfolio_id" in columns:
        return q, tuple(params or ())
    new_q = (
        match.group(1)
        + match.group(2)
        + ", user_id, portfolio_id"
        + match.group(3)
        + match.group(4)
        + ", %s, %s"
        + match.group(5)
    )
    return new_q, tuple(params or ()) + (ctx.user_id, ctx.portfolio_id)


def _scope_select(query: str, params: Tuple[Any, ...], ctx: TenantContext):
    q = str(query or "")
    tables = {
        _normalise_table(name)
        for name in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", q, flags=re.IGNORECASE)
    }
    scoped = tables & SCOPED_TABLES
    if not scoped:
        return q, tuple(params or ())
    if len(tables) != 1:
        return q, tuple(params or ())
    return _append_scope_predicate(q, tuple(params or ()), ctx)


def _make_wrappers(ctx: TenantContext):
    def fetch_table_scoped(table: str):
        table_name = _normalise_table(table)
        if table_name not in SCOPED_TABLES:
            return _ORIGINAL_FETCH_TABLE(table)
        return _ORIGINAL_FETCH_DF(
            f"SELECT * FROM {_safe_ident(table_name)} WHERE user_id=%s AND portfolio_id=%s",
            (ctx.user_id, ctx.portfolio_id),
        )

    def fetch_df_scoped(query: str, params: Optional[Tuple[Any, ...]] = None):
        q, p = _scope_select(query, tuple(params or ()), ctx)
        return _ORIGINAL_FETCH_DF(q, p)

    def execute_query_scoped(query: str, params: Optional[Tuple[Any, ...]] = None) -> bool:
        table = _extract_write_table(query)
        if table not in SCOPED_TABLES:
            return bool(_ORIGINAL_EXECUTE_QUERY(query, tuple(params or ())))
        if re.match(r"^\s*INSERT", str(query), flags=re.IGNORECASE):
            q, p = _scope_insert(query, tuple(params or ()), ctx)
        else:
            q, p = _append_scope_predicate(query, tuple(params or ()), ctx)
        return bool(_ORIGINAL_EXECUTE_QUERY(q, p))

    return fetch_table_scoped, fetch_df_scoped, execute_query_scoped


def install_tenant_scope(username: str) -> TenantContext:
    """Install tenant-aware compatibility wrappers for the active session."""
    global _INSTALLED, _CONTEXT

    if _INSTALLED and _CONTEXT and _CONTEXT.username == str(username):
        return _CONTEXT

    if _ORIGINAL_FETCH_DF is None:
        raise RuntimeError("database.fetch_df غير متوفر")

    _ensure_portfolios_table()
    user_id = _resolve_user_id(username)
    portfolio_id = _ensure_default_portfolio(user_id)
    ctx = TenantContext(user_id=user_id, username=str(username), portfolio_id=portfolio_id)
    _ensure_scoped_columns()
    _claim_legacy_rows(ctx)

    fetch_table_scoped, fetch_df_scoped, execute_query_scoped = _make_wrappers(ctx)
    _db.fetch_table = fetch_table_scoped
    _db.fetch_df = fetch_df_scoped
    _db.execute_query = execute_query_scoped

    st.session_state["user_id"] = ctx.user_id
    st.session_state["portfolio_id"] = ctx.portfolio_id
    _CONTEXT = ctx
    _INSTALLED = True
    return ctx


def current_tenant() -> Optional[TenantContext]:
    return _CONTEXT


def scoped_sql_preview(query: str, params: Tuple[Any, ...], *, user_id: int = 7, portfolio_id: int = 11):
    """Pure helper used by tests to inspect write scoping."""
    ctx = TenantContext(user_id=user_id, username="test", portfolio_id=portfolio_id)
    table = _extract_write_table(query)
    if table not in SCOPED_TABLES:
        return query, params
    if re.match(r"^\s*INSERT", query, flags=re.IGNORECASE):
        return _scope_insert(query, params, ctx)
    return _append_scope_predicate(query, params, ctx)
