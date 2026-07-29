from __future__ import annotations

import inspect

import app
import database_pool_hardening_v6 as hardening


def test_app_installs_threadsafe_pool_before_database_initialization():
    source = inspect.getsource(app._init_db_once)
    install_position = source.index("install_threadsafe_database_pool()")
    import_position = source.index("from database import init_db")
    init_position = source.index("init_db()")
    assert install_position < import_position < init_position


def test_hardening_uses_psycopg_threaded_pool_and_serializes_initialization():
    source = inspect.getsource(hardening)
    assert "from psycopg2.pool import ThreadedConnectionPool" in source
    assert "from psycopg2.pool import SimpleConnectionPool" not in source
    assert "with _RESOURCE_LOCK" in source
    assert "database._POOL_IMPLEMENTATION" in source
    assert "OSOUL_DB_POOL_MIN" in source
    assert "OSOUL_DB_POOL_MAX" in source
    assert "pool.putconn(conn, close=closed)" in source
    assert '"pool_type": "ThreadedConnectionPool"' in source


def test_pool_defaults_are_sized_for_multiple_streamlit_sessions():
    assert hardening._bounded_int("MISSING_POOL_SETTING", 10, 1, 50) == 10
