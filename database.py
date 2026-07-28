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

warnings.filterwarnings(
    "ignore",
    message=r"pandas only supports SQLAlchemy connectable",
    category=UserWarning,
)


def _set_last_db_error(msg: str) -> None:
    try:
        st.session_state["_db_last_error"] = (msg or "")[:2000]
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Unable to store last database error"
        )


try:
    import psycopg2
    from psycopg2.pool import ThreadedConnectionPool
except Exception:
    psycopg2 = None
    ThreadedConnectionPool = None

import config

_POOL: Optional["ThreadedConnectionPool"] = None
_POOL_LAST_ERR: Optional[str] = None
_POOL_LAST_OK: bool = False
_POOL_LAST_CHECK: float = 0.0
_ENGINE: Any | None = None
_ENGINE_INITIALIZED: bool = False
_SQLITE_PATH = os.getenv("SQLITE_PATH", "osoul_local.db")
_ALLOW_SQLITE_FALLBACK: bool = bool(getattr(config, "ALLOW_SQLITE_FALLBACK", False))
_REQUIRE_DB: bool = bool(getattr(config, "REQUIRE_DB", True))


def _is_postgres_url(url: str) -> bool:
    u = (url or "").lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


def _get_db_url() -> str:
    return (
        getattr(config, "DB_CONNECTION_URL", None)
        or getattr(config, "DATABASE_URL", None)
        or ""
    ).strip()


def _get_db_kind() -> str:
    return "postgres" if _is_postgres_url(_get_db_url()) else "sqlite"


def _get_engine():
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
    """Return one process-wide pool safe for concurrent Streamlit threads."""
    global _POOL, _POOL_LAST_ERR, _POOL_LAST_OK, _POOL_LAST_CHECK
    now = time.time()
    if _POOL is not None and (now - _POOL_LAST_CHECK) < 2:
        return _POOL
    _POOL_LAST_CHECK = now
    db_url = _get_db_url()
    if not db_url:
        _POOL_LAST_ERR = "Missing DATABASE_URL"
        _POOL_LAST_OK = False
        return None
    if not _is_postgres_url(db_url):
        _POOL_LAST_ERR = "DATABASE_URL is not a Postgres URL (expected postgresql://...)"
        _POOL_LAST_OK = False
        return None
    if psycopg2 is None or ThreadedConnectionPool is None:
        _POOL_LAST_ERR = "psycopg2 is not available"
        _POOL_LAST_OK = False
        return None
    try:
        if _POOL is None:
            minconn = max(1, int(os.getenv("OSOUL_DB_POOL_MIN", "1")))
            maxconn = max(minconn, int(os.getenv("OSOUL_DB_POOL_MAX", "10")))
            _POOL = ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                dsn=db_url,
            )
        _POOL_LAST_OK = True
        _POOL_LAST_ERR = None
        return _POOL
    except Exception as exc:
        _POOL = None
        _POOL_LAST_OK = False
        _POOL_LAST_ERR = redact_text(exc)
        return None


def get_connection() -> Tuple[Any, str]:
    db_url = _get_db_url()
    pool = get_connection_pool()
    if pool is not None:
        try:
            conn = pool.getconn()
            if getattr(conn, "closed", 0):
                pool.putconn(conn, close=True)
                conn = pool.getconn()
            return conn, "postgres"
        except Exception as exc:
            global _POOL_LAST_ERR
            _POOL_LAST_ERR = redact_text(exc)
    if _ALLOW_SQLITE_FALLBACK or (not db_url and not _REQUIRE_DB):
        import sqlite3

        conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn, "sqlite"
    hint = "DATABASE_URL غير مضبوط أو تعذر الاتصال بقاعدة البيانات."
    if not db_url:
        hint = "DATABASE_URL غير موجود في Secrets/Env."
    elif _POOL_LAST_ERR:
        hint = f"تعذر الاتصال بقاعدة البيانات: {_POOL_LAST_ERR}"
    raise RuntimeError(hint)


def put_connection(conn, kind: str, *, close: bool = False):
    if not conn:
        return
    if kind == "postgres":
        pool = get_connection_pool()
        if pool is not None:
            try:
                pool.putconn(conn, close=bool(close or getattr(conn, "closed", 0)))
                return
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Unable to return PostgreSQL connection to pool"
                )
    try:
        conn.close()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Unable to close database connection")


def db_healthcheck() -> Dict[str, Any]:
    db_url = _get_db_url()
    out: Dict[str, Any] = {
        "ok": False,
        "kind": "none",
        "error": "",
        "has_db_url": bool(db_url),
        "pool_ok": bool(_POOL_LAST_OK),
        "pool_error": _POOL_LAST_ERR or "",
        "pool_type": "threaded" if ThreadedConnectionPool is not None else "unavailable",
    }
    try:
        conn, kind = get_connection()
        try:
            cur = conn.cursor() if hasattr(conn, "cursor") else None
            if cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            out["ok"] = True
            out["kind"] = kind
            return out
        finally:
            put_connection(conn, kind)
    except Exception as exc:
        out["error"] = redact_text(exc)
        return out


def _adapt_query_for_kind(query: str, kind: str) -> str:
    q = str(query or "")
    if kind == "sqlite":
        q = q.replace("%s", "?")
        q = re.sub(r"\bBIGSERIAL\b", "INTEGER", q, flags=re.IGNORECASE)
        q = re.sub(r"\bSERIAL\b", "INTEGER", q, flags=re.IGNORECASE)
    return q


def execute_query(query: str, params: tuple = ()) -> bool:
    conn = None
    kind = ""
    try:
        conn, kind = get_connection()
        cur = conn.cursor()
        cur.execute(_adapt_query_for_kind(query, kind), tuple(params or ()))
        conn.commit()
        return True
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        _set_last_db_error(redact_text(exc))
        return False
    finally:
        if conn is not None:
            put_connection(conn, kind)


def execute_query_rowcount(query: str, params: tuple = ()) -> int:
    """Execute one write and return affected rows; -1 means execution failure."""
    conn = None
    kind = ""
    try:
        conn, kind = get_connection()
        cur = conn.cursor()
        cur.execute(_adapt_query_for_kind(query, kind), tuple(params or ()))
        rowcount = int(cur.rowcount if cur.rowcount is not None else 0)
        conn.commit()
        return max(0, rowcount)
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        _set_last_db_error(redact_text(exc))
        return -1
    finally:
        if conn is not None:
            put_connection(conn, kind)


def fetch_df(query: str, params: tuple = ()) -> pd.DataFrame:
    engine = _get_engine()
    if engine is not None:
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                return pd.read_sql_query(text(query), conn, params=tuple(params or ()))
        except Exception as exc:
            _set_last_db_error(redact_text(exc))
    conn = None
    kind = ""
    try:
        conn, kind = get_connection()
        return pd.read_sql_query(
            _adapt_query_for_kind(query, kind),
            conn,
            params=tuple(params or ()),
        )
    except Exception as exc:
        _set_last_db_error(redact_text(exc))
        return pd.DataFrame()
    finally:
        if conn is not None:
            put_connection(conn, kind)


def fetch_table(table: str) -> pd.DataFrame:
    name = str(table or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("invalid table name")
    return fetch_df(f"SELECT * FROM {name}")


def table_exists(table: str) -> bool:
    name = str(table or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return False
    conn = None
    kind = ""
    try:
        conn, kind = get_connection()
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name=%s)",
                (name.lower(),),
            )
            return bool(cur.fetchone()[0])
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        )
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        if conn is not None:
            put_connection(conn, kind)
