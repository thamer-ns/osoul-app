"""Install a configurable thread-safe Psycopg2 pool before first use."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_RESOURCE_LOCK = threading.RLock()
_INSTALLED = False
_POOL_MIN = 1
_POOL_MAX = 10


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(minimum, min(maximum, value))


def install_threadsafe_database_pool() -> None:
    global _INSTALLED, _POOL_MIN, _POOL_MAX
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import database

        try:
            from psycopg2.pool import ThreadedConnectionPool
        except Exception:
            LOGGER.info("ThreadedConnectionPool unavailable; retaining configured fallback")
            _INSTALLED = True
            return

        _POOL_MIN = _bounded_int("OSOUL_DB_POOL_MIN", 1, 1, 20)
        _POOL_MAX = _bounded_int("OSOUL_DB_POOL_MAX", 10, _POOL_MIN, 50)
        existing = getattr(database, "_POOL", None)
        if existing is not None and not isinstance(existing, ThreadedConnectionPool):
            try:
                existing.closeall()
            except Exception:
                LOGGER.warning("Unable to close legacy connection pool cleanly", exc_info=True)
            database._POOL = None  # noqa: SLF001

        def configured_threaded_pool(*args: Any, **kwargs: Any):
            dsn = kwargs.get("dsn")
            if dsn is None and len(args) >= 3:
                dsn = args[2]
            return ThreadedConnectionPool(
                minconn=_POOL_MIN,
                maxconn=_POOL_MAX,
                dsn=dsn,
            )

        configured_threaded_pool.__name__ = "ConfiguredThreadedConnectionPool"
        database.SimpleConnectionPool = configured_threaded_pool
        database.ThreadedConnectionPool = ThreadedConnectionPool

        original_pool_factory = database.get_connection_pool
        original_engine_factory = getattr(database, "_get_engine", None)
        original_get_connection = database.get_connection
        original_put_connection = database.put_connection
        original_healthcheck = database.db_healthcheck

        def get_connection_pool_threadsafe(*args: Any, **kwargs: Any):
            with _RESOURCE_LOCK:
                return original_pool_factory(*args, **kwargs)

        def get_connection_threadsafe(*args: Any, **kwargs: Any):
            conn, kind = original_get_connection(*args, **kwargs)
            if kind != "postgres" or not getattr(conn, "closed", 0):
                return conn, kind
            pool = get_connection_pool_threadsafe()
            if pool is not None:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    LOGGER.warning("Unable to discard closed pooled connection", exc_info=True)
            conn, kind = original_get_connection(*args, **kwargs)
            if kind == "postgres" and getattr(conn, "closed", 0):
                raise RuntimeError("PostgreSQL pool returned a closed connection")
            return conn, kind

        def put_connection_threadsafe(conn: Any, kind: str):
            if not conn:
                return
            if kind != "postgres":
                return original_put_connection(conn, kind)
            pool = get_connection_pool_threadsafe()
            if pool is None:
                try:
                    conn.close()
                except Exception:
                    LOGGER.warning("Unable to close detached PostgreSQL connection", exc_info=True)
                return
            closed = bool(getattr(conn, "closed", 0))
            if not closed:
                try:
                    conn.rollback()
                except Exception:
                    closed = True
                    LOGGER.warning("Pooled connection rollback failed; discarding it", exc_info=True)
            try:
                pool.putconn(conn, close=closed)
            except Exception:
                LOGGER.warning("Unable to return PostgreSQL connection to pool", exc_info=True)
                try:
                    conn.close()
                except Exception:
                    LOGGER.debug("Unable to close failed pooled connection", exc_info=True)

        def db_healthcheck_threadsafe() -> dict[str, Any]:
            result = dict(original_healthcheck())
            result.update(
                {
                    "pool_type": "ThreadedConnectionPool",
                    "pool_min": _POOL_MIN,
                    "pool_max": _POOL_MAX,
                }
            )
            return result

        database.get_connection_pool = get_connection_pool_threadsafe
        database.get_connection = get_connection_threadsafe
        database.put_connection = put_connection_threadsafe
        database.db_healthcheck = db_healthcheck_threadsafe

        if callable(original_engine_factory):
            def get_engine_threadsafe(*args: Any, **kwargs: Any):
                with _RESOURCE_LOCK:
                    return original_engine_factory(*args, **kwargs)

            database._get_engine = get_engine_threadsafe  # noqa: SLF001

        database._POOL_IMPLEMENTATION = "ThreadedConnectionPool"  # noqa: SLF001
        database._POOL_MIN_CONFIGURED = _POOL_MIN  # noqa: SLF001
        database._POOL_MAX_CONFIGURED = _POOL_MAX  # noqa: SLF001
        _INSTALLED = True


def pool_hardening_status() -> dict[str, Any]:
    try:
        import database

        return {
            "installed": _INSTALLED,
            "implementation": getattr(database, "_POOL_IMPLEMENTATION", None),
            "factory": getattr(getattr(database, "SimpleConnectionPool", None), "__name__", None),
            "minconn": getattr(database, "_POOL_MIN_CONFIGURED", _POOL_MIN),
            "maxconn": getattr(database, "_POOL_MAX_CONFIGURED", _POOL_MAX),
        }
    except Exception:
        return {
            "installed": False,
            "implementation": None,
            "factory": None,
            "minconn": None,
            "maxconn": None,
        }


__all__ = ["install_threadsafe_database_pool", "pool_hardening_status"]
