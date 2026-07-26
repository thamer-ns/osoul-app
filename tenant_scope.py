"""Per-session database isolation for Osoli.

The database wrapper is installed once per Python process, but it resolves the
active tenant from Streamlit ``session_state`` on every query. Module globals
are shared by concurrent Streamlit sessions, so no user identity is stored in a
global closure.
"""
from __future__ import annotations

import os
import re
import threading
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
TENANT_SYMBOL_TABLES = {"watchlist", "investmentthesis"}

_ORIGINAL_FETCH_TABLE = _db.fetch_table
_ORIGINAL_FETCH_DF = getattr(_db, "fetch_df", None)
_ORIGINAL_EXECUTE_QUERY = _db.execute_query
_WRAPPERS_INSTALLED = False
_SCHEMA_READY = False
_INSTALL_LOCK = threading.RLock()


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


def _session_context(*, required: bool = True) -> Optional[TenantContext]:
    try:
        user_id = st.session_state.get("user_id")
        username = st.session_state.get("username")
        portfolio_id = st.session_state.get("portfolio_id")
    except Exception:
        user_id = username = portfolio_id = None
    if user_id is None or portfolio_id is None or not username:
        if required:
            raise RuntimeError("لا يوجد سياق مستخدم نشط لعملية مالية")
        return None
    return TenantContext(int(user_id), str(username), int(portfolio_id))


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


def _add_column_if_missing(
    table: str,
    column: str,
    sql_type: str = "INTEGER",
) -> None:
    if not _table_exists(table) or column.lower() in _table_columns(table):
        return
    if _connection_kind() == "postgres":
        query = (
            f"ALTER TABLE {_safe_ident(table)} ADD COLUMN IF NOT EXISTS "
            f"{_safe_ident(column)} {sql_type}"
        )
    else:
        query = (
            f"ALTER TABLE {_safe_ident(table)} ADD COLUMN "
            f"{_safe_ident(column)} {sql_type}"
        )
    if not _ORIGINAL_EXECUTE_QUERY(query):
        raise RuntimeError(f"تعذر إضافة العمود {column} إلى {table}")


def _ensure_portfolios_table() -> None:
    if _connection_kind() == "postgres":
        query = """
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
        query = """
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
    if not _ORIGINAL_EXECUTE_QUERY(query):
        raise RuntimeError("تعذر إنشاء جدول المحافظ")
    if not _ORIGINAL_EXECUTE_QUERY(
        "CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id)"
    ):
        raise RuntimeError("تعذر إنشاء فهرس المحافظ")


def _ensure_scoped_columns() -> None:
    for table in SCOPED_TABLES:
        if not _table_exists(table):
            continue
        _add_column_if_missing(table, "user_id", "INTEGER")
        _add_column_if_missing(table, "portfolio_id", "INTEGER")
        if not _ORIGINAL_EXECUTE_QUERY(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant "
            f"ON {table}(user_id, portfolio_id)"
        ):
            raise RuntimeError(f"تعذر إنشاء فهرس العزل لجدول {table}")


def _sqlite_has_global_symbol_unique(cur, table: str) -> bool:
    cur.execute(f"PRAGMA index_list({_safe_ident(table)})")
    for row in cur.fetchall() or []:
        index_name = str(row[1])
        is_unique = bool(row[2])
        if not is_unique:
            continue
        cur.execute(f"PRAGMA index_info({_safe_ident(index_name)})")
        columns = [str(item[2]).lower() for item in (cur.fetchall() or [])]
        if columns == ["symbol"]:
            return True
    return False


def _migrate_sqlite_symbol_tables(conn) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=OFF")
    if _table_exists("watchlist") and _sqlite_has_global_symbol_unique(
        cur, "watchlist"
    ):
        cur.execute(
            """
            CREATE TABLE watchlist_tenant_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                created_at TEXT,
                user_id INTEGER,
                portfolio_id INTEGER,
                UNIQUE(user_id, portfolio_id, symbol)
            )
            """
        )
        cur.execute(
            """
            INSERT INTO watchlist_tenant_new
                (id, symbol, created_at, user_id, portfolio_id)
            SELECT id, symbol, created_at, user_id, portfolio_id
            FROM watchlist
            """
        )
        cur.execute("DROP TABLE watchlist")
        cur.execute("ALTER TABLE watchlist_tenant_new RENAME TO watchlist")

    if _table_exists("investmentthesis"):
        columns = _table_columns("investmentthesis")
        if "id" not in columns:
            cur.execute(
                """
                CREATE TABLE investmentthesis_tenant_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    thesis_text TEXT,
                    target_price REAL,
                    recommendation TEXT,
                    last_updated TEXT,
                    user_id INTEGER,
                    portfolio_id INTEGER,
                    UNIQUE(user_id, portfolio_id, symbol)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO investmentthesis_tenant_new
                    (symbol, thesis_text, target_price, recommendation,
                     last_updated, user_id, portfolio_id)
                SELECT symbol, thesis_text, target_price, recommendation,
                       last_updated, user_id, portfolio_id
                FROM investmentthesis
                """
            )
            cur.execute("DROP TABLE investmentthesis")
            cur.execute(
                "ALTER TABLE investmentthesis_tenant_new "
                "RENAME TO investmentthesis"
            )
    cur.execute("PRAGMA foreign_keys=ON")


def _migrate_postgres_symbol_tables(conn) -> None:
    cur = conn.cursor()
    if _table_exists("watchlist"):
        cur.execute(
            "ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS "
            "watchlist_symbol_key"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_watchlist_tenant_symbol ON "
            "watchlist(user_id, portfolio_id, symbol)"
        )
    if _table_exists("investmentthesis"):
        cur.execute(
            "ALTER TABLE investmentthesis ADD COLUMN IF NOT EXISTS "
            "id BIGSERIAL"
        )
        cur.execute(
            "ALTER TABLE investmentthesis DROP CONSTRAINT IF EXISTS "
            "investmentthesis_pkey"
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname='investmentthesis_pkey'
                      AND conrelid='investmentthesis'::regclass
                ) THEN
                    ALTER TABLE investmentthesis
                    ADD CONSTRAINT investmentthesis_pkey PRIMARY KEY (id);
                END IF;
            END $$;
            """
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_investmentthesis_tenant_symbol ON "
            "investmentthesis(user_id, portfolio_id, symbol)"
        )


def _migrate_tenant_symbol_constraints() -> None:
    conn, kind = _db.get_connection()
    try:
        if kind == "postgres":
            _migrate_postgres_symbol_tables(conn)
        else:
            _migrate_sqlite_symbol_tables(conn)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _db.put_connection(conn, kind)


def _ensure_schema_once() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _INSTALL_LOCK:
        if _SCHEMA_READY:
            return
        _ensure_portfolios_table()
        _ensure_scoped_columns()
        _migrate_tenant_symbol_constraints()
        _SCHEMA_READY = True


def _resolve_user_id(username: str) -> int:
    if _ORIGINAL_FETCH_DF is None:
        raise RuntimeError("database.fetch_df غير متوفر")
    frame = _ORIGINAL_FETCH_DF(
        "SELECT id FROM users WHERE username=%s LIMIT 1",
        (str(username),),
    )
    if frame is None or frame.empty:
        raise RuntimeError("تعذر تحديد المستخدم الحالي")
    return int(frame.iloc[0]["id"])


def _ensure_default_portfolio(user_id: int) -> int:
    frame = _ORIGINAL_FETCH_DF(
        "SELECT id FROM portfolios WHERE user_id=%s "
        "ORDER BY is_default DESC, id ASC LIMIT 1",
        (int(user_id),),
    )
    if frame is not None and not frame.empty:
        return int(frame.iloc[0]["id"])
    if not _ORIGINAL_EXECUTE_QUERY(
        "INSERT INTO portfolios "
        "(user_id, name, base_currency, is_default) "
        "VALUES (%s,%s,%s,%s)",
        (int(user_id), "المحفظة الرئيسية", "SAR", 1),
    ):
        raise RuntimeError("تعذر إنشاء المحفظة الافتراضية")
    frame = _ORIGINAL_FETCH_DF(
        "SELECT id FROM portfolios WHERE user_id=%s "
        "ORDER BY id DESC LIMIT 1",
        (int(user_id),),
    )
    if frame is None or frame.empty:
        raise RuntimeError("تعذر قراءة المحفظة الافتراضية")
    return int(frame.iloc[0]["id"])


def _claim_legacy_rows(ctx: TenantContext) -> None:
    users = _ORIGINAL_FETCH_DF("SELECT COUNT(*) AS n FROM users")
    user_count = (
        int(users.iloc[0]["n"])
        if users is not None and not users.empty
        else 0
    )
    force = os.getenv("OSOUL_CLAIM_LEGACY_DATA", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    st.session_state.pop("_tenant_unclaimed_legacy", None)
    if user_count > 1 and not force:
        st.session_state["_tenant_unclaimed_legacy"] = True
        return
    for table in SCOPED_TABLES:
        if not _table_exists(table):
            continue
        columns = _table_columns(table)
        if {"user_id", "portfolio_id"}.issubset(columns):
            if not _ORIGINAL_EXECUTE_QUERY(
                f"UPDATE {table} SET user_id=%s, portfolio_id=%s "
                "WHERE user_id IS NULL OR portfolio_id IS NULL",
                (ctx.user_id, ctx.portfolio_id),
            ):
                raise RuntimeError(
                    f"تعذر ترحيل البيانات القديمة في {table}"
                )


def _normalise_table(name: str) -> str:
    return str(name or "").strip().strip('"').split(".")[-1].lower()


def _extract_write_table(query: str) -> Optional[str]:
    for pattern in (
        r"^\s*INSERT(?:\s+OR\s+REPLACE)?\s+INTO\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*UPDATE\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*DELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)",
    ):
        match = re.search(
            pattern,
            str(query or ""),
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return _normalise_table(match.group(1))
    return None


def _append_scope_predicate(
    query: str,
    params: Tuple[Any, ...],
    ctx: TenantContext,
) -> tuple[str, tuple[Any, ...]]:
    scoped_query = str(query or "").strip()
    semicolon = scoped_query.endswith(";")
    if semicolon:
        scoped_query = scoped_query[:-1].rstrip()
    suffix = ""
    match = re.search(
        r"\s+(RETURNING|ORDER\s+BY|LIMIT)\s+",
        scoped_query,
        flags=re.IGNORECASE,
    )
    if match:
        suffix = scoped_query[match.start() :]
        scoped_query = scoped_query[: match.start()].rstrip()
    predicate = "user_id=%s AND portfolio_id=%s"
    conjunction = (
        " AND "
        if re.search(r"\bWHERE\b", scoped_query, re.IGNORECASE)
        else " WHERE "
    )
    scoped_query = (
        f"{scoped_query}{conjunction}{predicate}"
        f"{suffix}{';' if semicolon else ''}"
    )
    return (
        scoped_query,
        tuple(params or ()) + (ctx.user_id, ctx.portfolio_id),
    )


def _scope_insert(
    query: str,
    params: Tuple[Any, ...],
    ctx: TenantContext,
) -> tuple[str, tuple[Any, ...]]:
    table = _extract_write_table(query)
    match = re.match(
        r"^(\s*INSERT(?:\s+OR\s+REPLACE)?\s+INTO\s+"
        r"[A-Za-z_][A-Za-z0-9_]*\s*\()([^)]*)"
        r"(\)\s*VALUES\s*\()([^)]*)(\).*)$",
        str(query or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError("صيغة INSERT غير مدعومة للجدول المعزول")
    columns = [
        column.strip().strip('"').lower()
        for column in match.group(2).split(",")
    ]
    has_user = "user_id" in columns
    has_portfolio = "portfolio_id" in columns
    if has_user != has_portfolio:
        raise ValueError("يجب تمرير user_id وportfolio_id معًا")
    if has_user and has_portfolio:
        scoped_query = str(query)
        scoped_params = tuple(params or ())
    else:
        scoped_query = (
            match.group(1)
            + match.group(2)
            + ", user_id, portfolio_id"
            + match.group(3)
            + match.group(4)
            + ", %s, %s"
            + match.group(5)
        )
        scoped_params = tuple(params or ()) + (
            ctx.user_id,
            ctx.portfolio_id,
        )
    if table in TENANT_SYMBOL_TABLES:
        scoped_query = re.sub(
            r"ON\s+CONFLICT\s*\(\s*symbol\s*\)",
            "ON CONFLICT (user_id, portfolio_id, symbol)",
            scoped_query,
            flags=re.IGNORECASE,
        )
    return scoped_query, scoped_params


def _scope_select(
    query: str,
    params: Tuple[Any, ...],
    ctx: TenantContext,
) -> tuple[str, tuple[Any, ...]]:
    raw_query = str(query or "")
    tables = {
        _normalise_table(name)
        for name in re.findall(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",
            raw_query,
            flags=re.IGNORECASE,
        )
    }
    scoped_tables = tables & SCOPED_TABLES
    if not scoped_tables:
        return raw_query, tuple(params or ())
    if len(tables) != 1:
        lower = raw_query.lower()
        if "user_id" in lower and "portfolio_id" in lower:
            return raw_query, tuple(params or ())
        raise ValueError(
            "استعلام الربط المالي يجب أن يحدد عزل المستخدم صراحة"
        )
    return _append_scope_predicate(raw_query, tuple(params or ()), ctx)


def _query_uses_scoped_table(query: str) -> bool:
    tables = {
        _normalise_table(name)
        for name in re.findall(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",
            str(query or ""),
            flags=re.IGNORECASE,
        )
    }
    return bool(tables & SCOPED_TABLES)


def _install_generic_wrappers_once() -> None:
    global _WRAPPERS_INSTALLED
    if _WRAPPERS_INSTALLED:
        return
    with _INSTALL_LOCK:
        if _WRAPPERS_INSTALLED:
            return

        def fetch_table_scoped(table: str):
            table_name = _normalise_table(table)
            if table_name not in SCOPED_TABLES:
                return _ORIGINAL_FETCH_TABLE(table)
            ctx = _session_context(required=True)
            return _ORIGINAL_FETCH_DF(
                f"SELECT * FROM {_safe_ident(table_name)} "
                "WHERE user_id=%s AND portfolio_id=%s",
                (ctx.user_id, ctx.portfolio_id),
            )

        def fetch_df_scoped(
            query: str,
            params: Optional[Tuple[Any, ...]] = None,
        ):
            if not _query_uses_scoped_table(query):
                return _ORIGINAL_FETCH_DF(query, tuple(params or ()))
            ctx = _session_context(required=True)
            scoped_query, scoped_params = _scope_select(
                query,
                tuple(params or ()),
                ctx,
            )
            return _ORIGINAL_FETCH_DF(scoped_query, scoped_params)

        def execute_query_scoped(
            query: str,
            params: Optional[Tuple[Any, ...]] = None,
        ) -> bool:
            table = _extract_write_table(query)
            if table not in SCOPED_TABLES:
                return bool(
                    _ORIGINAL_EXECUTE_QUERY(query, tuple(params or ()))
                )
            ctx = _session_context(required=True)
            if re.match(r"^\s*INSERT", str(query), flags=re.IGNORECASE):
                scoped_query, scoped_params = _scope_insert(
                    query,
                    tuple(params or ()),
                    ctx,
                )
            else:
                scoped_query, scoped_params = _append_scope_predicate(
                    query,
                    tuple(params or ()),
                    ctx,
                )
            return bool(
                _ORIGINAL_EXECUTE_QUERY(scoped_query, scoped_params)
            )

        _db.fetch_table = fetch_table_scoped
        _db.fetch_df = fetch_df_scoped
        _db.execute_query = execute_query_scoped
        _WRAPPERS_INSTALLED = True


def install_tenant_scope(username: str) -> TenantContext:
    """Resolve this session's tenant and install fail-closed DB wrappers."""
    if _ORIGINAL_FETCH_DF is None:
        raise RuntimeError("database.fetch_df غير متوفر")
    _ensure_schema_once()
    user_id = _resolve_user_id(username)
    portfolio_id = _ensure_default_portfolio(user_id)
    ctx = TenantContext(user_id, str(username), portfolio_id)
    st.session_state["user_id"] = ctx.user_id
    st.session_state["portfolio_id"] = ctx.portfolio_id
    _claim_legacy_rows(ctx)
    _install_generic_wrappers_once()
    return ctx


def current_tenant() -> Optional[TenantContext]:
    return _session_context(required=False)


def scoped_sql_preview(
    query: str,
    params: Tuple[Any, ...],
    *,
    user_id: int = 7,
    portfolio_id: int = 11,
):
    """Pure helper used by tests to inspect write scoping."""
    ctx = TenantContext(
        user_id=user_id,
        username="test",
        portfolio_id=portfolio_id,
    )
    table = _extract_write_table(query)
    if table not in SCOPED_TABLES:
        return query, params
    if re.match(r"^\s*INSERT", query, flags=re.IGNORECASE):
        return _scope_insert(query, params, ctx)
    return _append_scope_predicate(query, params, ctx)
