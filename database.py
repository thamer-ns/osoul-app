# database.py

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

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

# If Postgres is not configured, fallback to sqlite for basic local usage
_SQLITE_PATH = os.getenv("SQLITE_PATH", "osoul_local.db")


def _is_postgres_url(url: str) -> bool:
    u = (url or "").lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


def _get_db_url() -> str:
    """Return DB URL from config/env/secrets (preferred)."""
    return (getattr(config, "DB_CONNECTION_URL", None) or getattr(config, "DATABASE_URL", None) or "").strip()


def get_connection_pool():
    """Get or create a Postgres connection pool, if configured.

    Notes:
    - إذا كان DATABASE_URL مهيأ كـ Postgres، لا نرجع لِـ SQLite بصمت عند فشل الاتصال.
      هذا كان يسبب: جداول (مثل users) تُقرأ من SQLite الفارغ => "خطأ في البيانات" حتى لو البيانات صحيحة.
    """
    global _POOL, _POOL_LAST_ERR, _POOL_LAST_OK, _POOL_LAST_CHECK

    now = time.time()
    # rate-limit pool init checks (خفيف لتجنب ضغط الاتصال)
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
        _POOL_LAST_ERR = "DATABASE_URL is not a Postgres URL"
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
        _POOL_LAST_ERR = str(e)
        return None


def get_connection():
    """Get a DB connection.

    - إذا كان DATABASE_URL مهيأ كـ Postgres: نحاول Postgres. إذا فشل => نرفع خطأ واضح.
      (لا fallback إلى SQLite بصمت)
    - إذا لم يكن هناك DATABASE_URL Postgres: نستخدم SQLite fallback.
    """
    db_url = _get_db_url()
    pool = get_connection_pool()

    # Postgres configured path
    if db_url and _is_postgres_url(db_url):
        if pool is None:
            raise RuntimeError(f"Postgres configured but connection pool is unavailable: {_POOL_LAST_ERR or 'unknown error'}")
        try:
            return pool.getconn(), "postgres"
        except Exception as e:
            raise RuntimeError(f"Failed to acquire Postgres connection from pool: {e}") from e

    # SQLite fallback (local/dev)
    try:
        import sqlite3
        conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
        return conn, "sqlite"
    except Exception as e:
        raise RuntimeError(f"Failed to open sqlite fallback: {e}") from e


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
                pass
    try:
        conn.close()
    except Exception:
        pass


def db_healthcheck() -> Dict[str, Any]:
    """
    Simple healthcheck that UI can call.
    Returns:
      { ok: bool, kind: 'postgres'|'sqlite'|..., error: str }
    """
    try:
        conn, kind = get_connection()
        try:
            # light query
            cur = conn.cursor() if hasattr(conn, "cursor") else None
            if cur:
                cur.execute("SELECT 1")
                _ = cur.fetchone()
            return {"ok": True, "kind": kind, "error": ""}
        finally:
            put_connection(conn, kind)
    except Exception as e:
        return {"ok": False, "kind": "none", "error": str(e)}


# ============================================================
# Helpers
# ============================================================

def execute_query(query: str, params: Optional[Tuple[Any, ...]] = None) -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
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


def fetch_table(t: str) -> pd.DataFrame:
    conn, kind = get_connection()
    try:
        return pd.read_sql(f"SELECT * FROM {t}", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        put_connection(conn, kind)


def fetch_df(query: str, params: Optional[Tuple[Any, ...]] = None) -> pd.DataFrame:
    """Fetch a DataFrame using a SQL query.

    لماذا؟
    - جلب جداول كبيرة كاملة ثم فلترتها في Pandas يسبب بطء/ذاكرة وقد يرجع DataFrame فاضي في بيئات Streamlit.
    - نحتاج استعلامات مفلترة (مثل financialstatements) حتى تظهر البيانات دائماً.

    ملاحظة: نستخدم pd.read_sql_query مع params.
    """
    conn, kind = get_connection()
    try:
        return pd.read_sql_query(query, conn, params=params or ())
    except Exception:
        return pd.DataFrame()
    finally:
        put_connection(conn, kind)


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


def db_get_user_schema(username: str) -> str:
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
                pass
            if "password" in cols:
                try:
                    cur.execute(
                        "UPDATE users SET password_hash = password WHERE password_hash IS NULL AND password IS NOT NULL"
                    )
                except Exception:
                    pass
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        put_connection(conn, kind)

def _hash_password(password: str) -> str:
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except Exception:
        # fallback (weak) — should not happen if bcrypt installed
        import hashlib

        return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _check_password(password: str, password_hash: str) -> bool:
    try:
        import bcrypt

        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        import hashlib

        return hashlib.sha256(password.encode("utf-8")).hexdigest() == (password_hash or "")


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
            pass
        return False
    finally:
        put_connection(conn, kind)


def db_verify_user(username: str, password: str) -> bool:
    ensure_users_table()
    try:
        conn, kind = get_connection()
    except RuntimeError as e:
        # لا نُرجع False (خطأ بيانات) عندما تكون المشكلة اتصال قاعدة البيانات
        raise
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
