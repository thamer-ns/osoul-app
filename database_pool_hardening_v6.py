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


def _prepare_postgres_connection(conn: Any) -> Any:
    """Return a clean read-write connection before application code uses it.

    Supavisor/pgbouncer sessions can retain transaction characteristics from a
    previous borrower or from connection-string options.  A pooled connection
    that starts its next transaction as read-only makes even idempotent schema
    checks fail with ``cannot execute CREATE TABLE in a read-only transaction``.
    Roll back any leftover transaction and make Psycopg start every subsequent
    transaction explicitly as READ WRITE.
    """
    if not conn or bool(getattr(conn, "closed", 0)):
        raise RuntimeError("PostgreSQL pool returned a closed connection")

    # A connection may be returned while PostgreSQL still considers it inside an
    # aborted/read-only transaction.  Reset that state before changing defaults.
    conn.rollback()

    set_session = getattr(conn, "set_session", None)
    if callable(set_session):
        set_session(readonly=False, autocommit=False)
    else:  # pragma: no cover - compatibility with simple test/dummy drivers
        setattr(conn, "readonly", False)
        setattr(conn, "autocommit", False)
    return conn


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

        def _discard(conn: Any) -> None:
            pool = get_connection_pool_threadsafe()
            if pool is not None:
                try:
                    pool.putconn(conn, close=True)
                    return
                except Exception:
                    LOGGER.warning(
                        "Unable to discard invalid pooled connection",
                        exc_info=True,
                    )
            try:
                conn.close()
            except Exception:
                LOGGER.debug("Unable to close invalid PostgreSQL connection", exc_info=True)

        def get_connection_threadsafe(*args: Any, **kwargs: Any):
            last_error: Exception | None = None
            for _attempt in range(2):
                conn, kind = original_get_connection(*args, **kwargs)
                if kind != "postgres":
                    return conn, kind
                if bool(getattr(conn, "closed", 0)):
                    last_error = RuntimeError(
                        "PostgreSQL pool returned a closed connection"
                    )
                    _discard(conn)
                    continue
                try:
                    return _prepare_postgres_connection(conn), kind
                except Exception as exc:
                    last_error = exc
                    LOGGER.warning(
                        "Unable to reset pooled PostgreSQL connection to read-write; "
                        "discarding it",
                        exc_info=True,
                    )
                    _discard(conn)
            raise RuntimeError(
                "PostgreSQL pool could not provide a clean read-write connection"
            ) from last_error

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
                    "pool_checkout_read_write_reset": True,
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
        database._POOL_READ_WRITE_RESET = True  # noqa: SLF001
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
            "checkout_read_write_reset": bool(
                getattr(database, "_POOL_READ_WRITE_RESET", False)
            ),
        }
    except Exception:
        return {
            "installed": False,
            "implementation": None,
            "factory": None,
            "minconn": None,
            "maxconn": None,
            "checkout_read_write_reset": False,
        }


__all__ = [
    "_prepare_postgres_connection",
    "install_threadsafe_database_pool",
    "pool_hardening_status",
]
