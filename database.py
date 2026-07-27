# database.py

from __future__ import annotations

import os
import re
import time
import warnings
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from osoli_logging import redact_text

# Silence pandas warning about DB-API connections (we still use parameterized queries safely)
warnings.filterwarnings(
    "ignore",
    message=r"pandas only supports SQLAlchemy connectable",
    category=UserWarning,
)


def _set_last_db_error(msg: str) -> None:
    """Store last DB error for UI debugging without crashing the app."""
    try:
        st.session_state["_db_last_error"] = (msg or "")[:2000]
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:28')

try:
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool
except Exception:
    psycopg2 = None
    SimpleConnectionPool = None

import config

# ============================================================
# DB Pool (Postgres) + Fallback (SQLite)
# ============================================================

_POOL: Optional["SimpleConnectionPool"] = None
_POOL_LAST_ERR: Optional[str] = None
_POOL_LAST_OK: bool = False
_POOL_LAST_CHECK: float = 0.0

# Optional SQLAlchemy engine for pandas (avoid repeated imports). If SQLAlchemy
# is not installed, we keep this as None and fall back to raw DB-API.
_ENGINE: Any | None = None
_ENGINE_INITIALIZED: bool = False

# If Postgres is not configured, fallback to sqlite for basic local usage
_SQLITE_PATH = os.getenv("SQLITE_PATH", "osoul_local.db")

# Production safety defaults (configurable via config.py/env)
_ALLOW_SQLITE_FALLBACK: bool = bool(getattr(config, "ALLOW_SQLITE_FALLBACK", False))
_REQUIRE_DB: bool = bool(getattr(config, "REQUIRE_DB", True))


def _is_postgres_url(url: str) -> bool:
    u = (url or "").lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


def _get_db_url() -> str:
    """Return DB URL from config/env/secrets (preferred)."""
    return (getattr(config, "DB_CONNECTION_URL", None) or getattr(config, "DATABASE_URL", None) or "").strip()

def _get_db_kind() -> str:
    url = _get_db_url()
    return "postgres" if _is_postgres_url(url) else "sqlite"


def _get_engine():
    """Create one SQLAlchemy engine for pandas reads, once per process."""
    global _ENGINE, _ENGINE_INITIALIZED
    if _ENGINE_INITIALIZED:
        return _ENGINE
    _ENGINE_INITIALIZED = True

    if _get_db_kind() != "postgres":
        _ENGINE = None
        return None

    db_url = _get_db_url()
    if not db_url:
        _ENGINE = None
        return None

    try:
        from sqlalchemy import create_engine  # type: ignore

        _ENGINE = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=2,
            future=True,
        )
    except Exception as exc:
        _ENGINE = None
        _set_last_db_error(f"sqlalchemy_engine_failed: {redact_text(exc)}")
    return _ENGINE



def get_connection_pool():
    """Get or create a Postgres connection pool, if configured."""
    global _POOL, _POOL_LAST_ERR, _POOL_LAST_OK, _POOL_LAST_CHECK

    # rate-limit pool init checks
    now = time.time()
    if _POOL is not None and (now - _POOL_LAST_CHECK) < 2:
        return _POOL

    _POOL_LAST_CHECK = now
    db_url = _get_db_url()

    if not db_url:
        _POOL_LAST_ERR = "Missing DATABASE_URL"
        _POOL_LAST_OK = False
        return None

    # If url isn't postgres, we won't create pool
    if not _is_postgres_url(db_url):
        _POOL_LAST_ERR = "DATABASE_URL is not a Postgres URL (expected postgresql://...)"
        _POOL_LAST_OK = False
        return None

    if psycopg2 is None or SimpleConnectionPool is None:
        _POOL_LAST_ERR = "psycopg2 is not available"
        _POOL_LAST_OK = False
        return None

    try:
        if _POOL is None:
            _POOL = SimpleConnectionPool(minconn=1, maxconn=5, dsn=db_url)
        _POOL_LAST_OK = True
        _POOL_LAST_ERR = None
        return _POOL
    except Exception as e:
        _POOL = None
        _POOL_LAST_OK = False
        _POOL_LAST_ERR = redact_text(e)
        return None


def get_connection() -> Tuple[Any, str]:
    """Get a DB connection.

    Priority:
    1) Postgres (DATABASE_URL)
    2) Optional SQLite fallback ONLY if OSOUL_ALLOW_SQLITE_FALLBACK=1

    In production we disable SQLite fallback by default to prevent accidental
    data loss / divergent state when Postgres is down.
    """
    db_url = _get_db_url()

    # 1) Postgres pool
    pool = get_connection_pool()
    if pool is not None:
        try:
            return pool.getconn(), "postgres"
        except Exception as e:
            # keep last error and proceed to fallback only if explicitly allowed
            global _POOL_LAST_ERR
            _POOL_LAST_ERR = redact_text(e)

    # 2) Optional SQLite fallback (dev only)
    if _ALLOW_SQLITE_FALLBACK or (not db_url and not _REQUIRE_DB):
        try:
            import sqlite3

            conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
            try:
                conn.execute("PRAGMA foreign_keys = ON;")
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:181')
            return conn, "sqlite"
        except Exception as e:
            raise RuntimeError(f"Failed to open sqlite fallback: {e}") from e

    # 3) Strict mode: no fallback
    hint = "DATABASE_URL غير مضبوط أو تعذر الاتصال بقاعدة البيانات."
    if not db_url:
        hint = "DATABASE_URL غير موجود في Secrets/Env."
    elif _POOL_LAST_ERR:
        hint = f"تعذر الاتصال بقاعدة البيانات: {_POOL_LAST_ERR}"
    raise RuntimeError(hint)


def put_connection(conn, kind: str):
    """Return connection to pool if postgres, otherwise close sqlite."""
    if not conn:
        return
    if kind == "postgres":
        pool = get_connection_pool()
        if pool is not None:
            try:
                pool.putconn(conn)
                return
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:206')
    try:
        conn.close()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:210')


def db_healthcheck() -> Dict[str, Any]:
    """
    Simple healthcheck that UI can call.
    Returns:
      { ok: bool, kind: 'postgres'|'sqlite'|..., error: str }
    """
    db_url = _get_db_url()
    out: Dict[str, Any] = {
        "ok": False,
        "kind": "none",
        "error": "",
        "has_db_url": bool(db_url),
        "pool_ok": bool(_POOL_LAST_OK),
        "pool_error": _POOL_LAST_ERR or "",
    }
    try:
        conn, kind = get_connection()
        try:
            # light query
            cur = conn.cursor() if hasattr(conn, "cursor") else None
            if cur:
                cur.execute("SELECT 1")
                _ = cur.fetchone()
            out["ok"] = True
            out["kind"] = kind
            return out
        finally:
            put_connection(conn, kind)
    except Exception as e:
        out["ok"] = False
        out["kind"] = "none"
        out["error"] = redact_text(e)
        return out


# ============================================================
# Helpers
# ============================================================


def _adapt_query_for_kind(query: str, kind: str) -> str:
    """Make SQL portable between Postgres (%s) and SQLite (?) and strip dialect-only syntax."""
    q = str(query or "")
    if kind == "sqlite":
        # placeholder style
        q = q.replace("%s", "?")
        # postgres casts
        q = re.sub(r"::\s*\w+", "", q)
        # NOW() -> CURRENT_TIMESTAMP
        q = q.replace("NOW()", "CURRENT_TIMESTAMP")
        q = q.replace("now()", "CURRENT_TIMESTAMP")
    return q


def _sqlalchemy_params(query: str, params: Optional[Tuple[Any, ...]]):
    """Convert DBAPI-style placeholders (%s) into SQLAlchemy text() params (:p0,:p1..).
    Works for simple positional params.
    """
    if params is None:
        return query, None
    q = str(query or "")
    values = list(params)
    out_params = {}
    # replace each %s sequentially
    idx = 0
    def repl(match):
        nonlocal idx
        key = f"p{idx}"
        out_params[key] = values[idx]
        idx += 1
        return f":{key}"
    # %s placeholders
    if "%s" in q:
        q2 = re.sub(r"%s", repl, q)
        return q2, out_params
    # ? placeholders
    if "?" in q:
        # replace ? one-by-one (avoid replacing question marks in strings is hard; assume safe here)
        def repl2(match):
            nonlocal idx
            key = f"p{idx}"
            out_params[key] = values[idx]
            idx += 1
            return f":{key}"
        q2 = re.sub(r"\?", repl2, q, count=len(values))
        return q2, out_params
    return q, out_params
def execute_query(query: str, params: Optional[Tuple[Any, ...]] = None) -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        q = _adapt_query_for_kind(query, kind)
        cur.execute(q, params or ())
        conn.commit()
        return True
    except Exception as e:
        _set_last_db_error(redact_text(e))
        try:
            conn.rollback()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:313')
        return False
    finally:
        put_connection(conn, kind)


def _safe_ident(name: str) -> str:
    """Allow only simple SQL identifiers to avoid injection."""
    n = (name or "").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", n):
        raise ValueError("Invalid identifier")
    return n


def fetch_table(t: str) -> pd.DataFrame:
    """Read a complete table without occupying two independent DB pools."""
    t = _safe_ident(t)
    kind = _get_db_kind()

    if kind == "postgres":
        engine = _get_engine()
        if engine is not None:
            queries = (
                f"SELECT * FROM {t}",
                f'SELECT * FROM "{t}"',
                f"SELECT * FROM public.{t}",
            )
            for query in queries:
                try:
                    # A successful empty result is still authoritative.  The
                    # old implementation retried two more queries and held a
                    # raw pooled connection at the same time.
                    return pd.read_sql(query, engine)
                except Exception as exc:
                    _set_last_db_error(redact_text(exc))

    conn = None
    actual_kind = kind
    try:
        conn, actual_kind = get_connection()
        if actual_kind == "postgres":
            try:
                return pd.read_sql(f"SELECT * FROM {t}", conn)
            except Exception:
                return pd.read_sql(f'SELECT * FROM "{t}"', conn)
        return pd.read_sql(f"SELECT * FROM {t}", conn)
    except Exception as exc:
        _set_last_db_error(redact_text(exc))
        return pd.DataFrame()
    finally:
        if conn is not None:
            put_connection(conn, actual_kind)


def fetch_df(query: str, params: Optional[Tuple[Any, ...]] = None) -> pd.DataFrame:
    """Fetch a parameterized dataframe using exactly one connection path."""
    kind = _get_db_kind()
    if kind == "postgres":
        engine = _get_engine()
        if engine is not None:
            try:
                from sqlalchemy import text as _sql_text

                adapted = _adapt_query_for_kind(query, "postgres")
                sql, bound = _sqlalchemy_params(adapted, params)
                if bound is None:
                    return pd.read_sql(sql, engine)
                return pd.read_sql(_sql_text(sql), engine, params=bound)
            except Exception as exc:
                _set_last_db_error(redact_text(exc))

    conn = None
    actual_kind = kind
    try:
        conn, actual_kind = get_connection()
        adapted = _adapt_query_for_kind(query, actual_kind)
        return pd.read_sql(adapted, conn, params=params or ())
    except Exception as exc:
        _set_last_db_error(redact_text(exc))
        return pd.DataFrame()
    finally:
        if conn is not None:
            put_connection(conn, actual_kind)


def _db_user_exists__shadowed_1(username: str) -> Optional[bool]:
    """Return True/False if known, or None if DB error."""
    u = (username or "").strip()
    if not u:
        return False
    try:
        df = fetch_df("SELECT 1 AS x FROM users WHERE username = %s LIMIT 1", (u,))
        if df is None:
            return None
        return not df.empty
    except Exception:
        # sqlite param placeholder differs, attempt fallback
        try:
            df = fetch_df("SELECT 1 AS x FROM users WHERE username = ? LIMIT 1", (u,))
            return not df.empty
        except Exception:
            return None



def table_exists(table_name: str) -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
                (table_name,),
            )
            return bool(cur.fetchone()[0])
        else:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        put_connection(conn, kind)


def ensure_table(query: str) -> bool:
    return execute_query(query)


# ============================================================
# Schema / Multi-user
# ============================================================

def get_user_schema(username: str) -> str:
    # default schema for single-tenant
    return "public"


def _db_get_user_schema__shadowed_1(username: str) -> str:
    return get_user_schema(username)


# ============================================================
# Users table (auth)
# ============================================================

def ensure_users_table():
    if table_exists("users"):
        _migrate_users_table_schema()
        return True

    # Note: SQLite and Postgres types differ; keep portable.
    q = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT,
        created_at TEXT
    );
    """
    if psycopg2 is not None and _is_postgres_url(_get_db_url()):
        # postgres flavor
        q = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            created_at TEXT
        );
        """

    return execute_query(q)



def _users_columns() -> set[str]:
    """Return set of column names in users table (lowercase)."""
    conn, kind = get_connection()
    cols: set[str] = set()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND table_schema=current_schema()"
            )
            cols = {str(r[0]).lower() for r in (cur.fetchall() or [])}
        else:
            cur.execute("PRAGMA table_info(users)")
            cols = {str(r[1]).lower() for r in (cur.fetchall() or [])}
    except Exception:
        cols = set()
    finally:
        put_connection(conn, kind)
    return cols


def _migrate_users_table_schema():
    """Backwards-compatible migration from older schema.

    Older versions used column name `password` (bcrypt hash).
    Newer code uses `password_hash`.
    We keep both and backfill `password_hash` from `password` if needed.
    """
    if not table_exists("users"):
        return

    cols = _users_columns()
    if "password_hash" in cols:
        return  # nothing to do

    # Add missing column then backfill
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
            # backfill when older column exists
            if "password" in cols:
                cur.execute(
                    "UPDATE users SET password_hash = password WHERE password_hash IS NULL AND password IS NOT NULL"
                )
        else:
            # SQLite: add column if missing
            try:
                cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:559')
            if "password" in cols:
                try:
                    cur.execute(
                        "UPDATE users SET password_hash = password WHERE password_hash IS NULL AND password IS NOT NULL"
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:566')
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:572')
    finally:
        put_connection(conn, kind)

def _hash_password(password: str) -> str:
    try:
        import bcrypt
    except Exception as exc:  # pragma: no cover - dependency is required
        raise RuntimeError("bcrypt مطلوب لتخزين كلمات المرور بأمان") from exc
    return bcrypt.hashpw(
        str(password).encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    try:
        import bcrypt
    except Exception as exc:  # pragma: no cover - dependency is required
        raise RuntimeError("bcrypt مطلوب للتحقق من كلمات المرور بأمان") from exc
    stored = str(password_hash or "")
    if not stored.startswith(("$2a$", "$2b$", "$2y$")):
        return False
    try:
        return bool(
            bcrypt.checkpw(
                str(password).encode("utf-8"),
                stored.encode("utf-8"),
            )
        )
    except Exception:
        return False


def db_user_exists(username: str) -> bool:
    ensure_users_table()
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute("SELECT 1 FROM users WHERE username=%s LIMIT 1", (username,))
        else:
            cur.execute("SELECT 1 FROM users WHERE username=? LIMIT 1", (username,))
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        put_connection(conn, kind)


def db_create_user(username: str, password: str, email: str = "") -> bool:
    ensure_users_table()
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        ph = _hash_password(password)
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")

        cols = _users_columns()
        pw_col = "password_hash" if "password_hash" in cols else ("password" if "password" in cols else "password_hash")

        if kind == "postgres":
            cur.execute(
                f"INSERT INTO users (username, {pw_col}, email, created_at) VALUES (%s, %s, %s, %s)",
                (username, ph, email or None, created_at),
            )
        else:
            cur.execute(
                f"INSERT INTO users (username, {pw_col}, email, created_at) VALUES (?, ?, ?, ?)",
                (username, ph, email or None, created_at),
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at database.py:642')
        return False
    finally:
        put_connection(conn, kind)


def db_verify_user(username: str, password: str) -> bool:
    ensure_users_table()
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        cols = _users_columns()
        pw_col = "password_hash" if "password_hash" in cols else ("password" if "password" in cols else "password_hash")

        if kind == "postgres":
            cur.execute(f"SELECT {pw_col} FROM users WHERE username=%s LIMIT 1", (username,))
        else:
            cur.execute(f"SELECT {pw_col} FROM users WHERE username=? LIMIT 1", (username,))
        row = cur.fetchone()
        if not row:
            return False
        ph = row[0] if isinstance(row, (tuple, list)) else row
        return _check_password(password, ph or "")
    except Exception:
        return False
    finally:
        put_connection(conn, kind)



# ============================================================
# Portfolio / Cashflow tables (Trades, Deposits, Withdrawals, Returns, Watchlist, Thesis)
# ============================================================

def ensure_portfolio_tables() -> bool:
    """Create all core portfolio tables if missing (portable Postgres/SQLite)."""
    is_pg = bool(psycopg2 is not None and _is_postgres_url(_get_db_url()))
    # Trades
    q_trades = """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        company_name TEXT,
        sector TEXT,
        asset_type TEXT,
        quantity REAL,
        entry_price REAL,
        exit_price REAL,
        current_price REAL,
        strategy TEXT,
        status TEXT,
        date TEXT,
        exit_date TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """
    if is_pg:
        q_trades = """
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            symbol TEXT,
            company_name TEXT,
            sector TEXT,
            asset_type TEXT,
            quantity DOUBLE PRECISION,
            entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION,
            current_price DOUBLE PRECISION,
            strategy TEXT,
            status TEXT,
            date TEXT,
            exit_date TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """

    q_deposits = """
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        amount REAL,
        note TEXT,
        created_at TEXT
    );
    """
    if is_pg:
        q_deposits = """
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            date TEXT,
            amount DOUBLE PRECISION,
            note TEXT,
            created_at TEXT
        );
        """

    q_withdrawals = """
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        amount REAL,
        note TEXT,
        created_at TEXT
    );
    """
    if is_pg:
        q_withdrawals = """
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            date TEXT,
            amount DOUBLE PRECISION,
            note TEXT,
            created_at TEXT
        );
        """

    q_returns = """
    CREATE TABLE IF NOT EXISTS returnsgrants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        symbol TEXT,
        amount REAL,
        note TEXT,
        created_at TEXT
    );
    """
    if is_pg:
        q_returns = """
        CREATE TABLE IF NOT EXISTS returnsgrants (
            id SERIAL PRIMARY KEY,
            date TEXT,
            symbol TEXT,
            amount DOUBLE PRECISION,
            note TEXT,
            created_at TEXT
        );
        """

    q_watch = """
    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT UNIQUE,
        created_at TEXT
    );
    """
    if is_pg:
        q_watch = """
        CREATE TABLE IF NOT EXISTS watchlist (
            id SERIAL PRIMARY KEY,
            symbol TEXT UNIQUE,
            created_at TEXT
        );
        """

    # thesis: one row per symbol
    q_thesis = """
    CREATE TABLE IF NOT EXISTS investmentthesis (
        symbol TEXT PRIMARY KEY,
        thesis_text TEXT,
        target_price REAL,
        recommendation TEXT,
        last_updated TEXT
    );
    """
    if is_pg:
        q_thesis = """
        CREATE TABLE IF NOT EXISTS investmentthesis (
            symbol TEXT PRIMARY KEY,
            thesis_text TEXT,
            target_price DOUBLE PRECISION,
            recommendation TEXT,
            last_updated TEXT
        );
        """

    ok = True
    for q in (q_trades, q_deposits, q_withdrawals, q_returns, q_watch, q_thesis):
        ok = execute_query(q) and ok
    return ok


# ============================================================
# Financial statements storage (light + raw json)
# ============================================================

def init_db():
    """
    Ensure core tables exist.
    Works for:
      - Postgres (public schema)
      - SQLite fallback
    """
    # users
    ensure_users_table()

    # core portfolio tables
    ensure_portfolio_tables()

    # lightweight financial table
    if not table_exists("financialstatements"):
        q = """
        CREATE TABLE IF NOT EXISTS financialstatements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            date_str TEXT,
            period_type TEXT,
            source TEXT,
            revenue REAL,
            net_income REAL,
            total_assets REAL,
            total_liabilities REAL,
            total_equity REAL,
            operating_cash_flow REAL,
            investing_cash_flow REAL,
            financing_cash_flow REAL,
            free_cash_flow REAL,
            current_assets REAL,
            current_liabilities REAL,
            long_term_debt REAL,
            gross_profit REAL,
            operating_income REAL,
            interest_expense REAL,
            ebitda REAL,
            shares_outstanding REAL,
            created_at TEXT
        );
        """
        if psycopg2 is not None and _is_postgres_url(_get_db_url()):
            q = """
            CREATE TABLE IF NOT EXISTS financialstatements (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                date_str TEXT,
                period_type TEXT,
                source TEXT,
                revenue DOUBLE PRECISION,
                net_income DOUBLE PRECISION,
                total_assets DOUBLE PRECISION,
                total_liabilities DOUBLE PRECISION,
                total_equity DOUBLE PRECISION,
                operating_cash_flow DOUBLE PRECISION,
                investing_cash_flow DOUBLE PRECISION,
                financing_cash_flow DOUBLE PRECISION,
                free_cash_flow DOUBLE PRECISION,
                current_assets DOUBLE PRECISION,
                current_liabilities DOUBLE PRECISION,
                long_term_debt DOUBLE PRECISION,
                gross_profit DOUBLE PRECISION,
                operating_income DOUBLE PRECISION,
                interest_expense DOUBLE PRECISION,
                ebitda DOUBLE PRECISION,
                shares_outstanding DOUBLE PRECISION,
                created_at TEXT
            );
            """
        execute_query(q)

    # Unique index required for ON CONFLICT upsert
    execute_query("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_financialstatements_uq
    ON financialstatements(symbol, date_str, period_type);
    """)

    # raw json table (full statements)
    if not table_exists("financialstatements_raw"):
        q = """
        CREATE TABLE IF NOT EXISTS financialstatements_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            date_str TEXT,
            period_type TEXT,
            source TEXT,
            payload TEXT,
            created_at TEXT
        );
        """
        if psycopg2 is not None and _is_postgres_url(_get_db_url()):
            q = """
            CREATE TABLE IF NOT EXISTS financialstatements_raw (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                date_str TEXT,
                period_type TEXT,
                source TEXT,
                payload TEXT,
                created_at TEXT
            );
            """
        execute_query(q)

    return True


# ============================================================
# Compatibility wrappers used by other modules
# ============================================================

def db_get_user_schema(username: str) -> str:
    return get_user_schema(username)


def fetch_table_safe(t: str) -> pd.DataFrame:
    try:
        return fetch_table(t)
    except Exception:
        return pd.DataFrame()
