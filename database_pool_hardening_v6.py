"""Install a thread-safe Psycopg2 pool before the first database connection.

Streamlit executes each session run in its own script thread.  The legacy module
imports ``SimpleConnectionPool`` and initialises process-global resources without
an initialisation lock.  This installer replaces the factory with
``ThreadedConnectionPool`` and serialises pool/engine creation while preserving
all public database APIs.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_RESOURCE_LOCK = threading.RLock()
_INSTALLED = False


def install_threadsafe_database_pool() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import database

        try:
            from psycopg2.pool import ThreadedConnectionPool
        except Exception:
            # SQLite/dev mode remains available; database.py will report missing
            # Psycopg in strict Postgres mode as it already does.
            LOGGER.info("ThreadedConnectionPool unavailable; retaining configured fallback")
            _INSTALLED = True
            return

        existing = getattr(database, "_POOL", None)
        if existing is not None and not isinstance(existing, ThreadedConnectionPool):
            try:
                existing.closeall()
            except Exception:
                LOGGER.warning("Unable to close legacy connection pool cleanly", exc_info=True)
            database._POOL = None  # noqa: SLF001

        # database.get_connection_pool resolves this module-global class at call
        # time, so replacing it before init_db changes the actual pool instance.
        database.SimpleConnectionPool = ThreadedConnectionPool
        database.ThreadedConnectionPool = ThreadedConnectionPool

        original_pool_factory = database.get_connection_pool
        original_engine_factory = getattr(database, "_get_engine", None)

        def get_connection_pool_threadsafe(*args: Any, **kwargs: Any):
            with _RESOURCE_LOCK:
                return original_pool_factory(*args, **kwargs)

        database.get_connection_pool = get_connection_pool_threadsafe

        if callable(original_engine_factory):
            def get_engine_threadsafe(*args: Any, **kwargs: Any):
                with _RESOURCE_LOCK:
                    return original_engine_factory(*args, **kwargs)

            database._get_engine = get_engine_threadsafe  # noqa: SLF001

        database._POOL_IMPLEMENTATION = "ThreadedConnectionPool"  # noqa: SLF001
        _INSTALLED = True


def pool_hardening_status() -> dict[str, Any]:
    try:
        import database

        return {
            "installed": _INSTALLED,
            "implementation": getattr(database, "_POOL_IMPLEMENTATION", None),
            "factory": getattr(getattr(database, "SimpleConnectionPool", None), "__name__", None),
        }
    except Exception:
        return {"installed": False, "implementation": None, "factory": None}


__all__ = ["install_threadsafe_database_pool", "pool_hardening_status"]
