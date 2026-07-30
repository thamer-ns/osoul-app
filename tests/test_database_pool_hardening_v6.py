from __future__ import annotations

import inspect

import app
import database_pool_hardening_v6 as hardening


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = 0
        self.rollback_calls = 0
        self.session_calls: list[dict[str, bool]] = []

    def rollback(self) -> None:
        self.rollback_calls += 1

    def set_session(self, **kwargs: bool) -> None:
        self.session_calls.append(dict(kwargs))


class _FallbackConnection:
    def __init__(self) -> None:
        self.closed = 0
        self.rollback_calls = 0
        self.readonly = True
        self.autocommit = True

    def rollback(self) -> None:
        self.rollback_calls += 1


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
    assert "_prepare_postgres_connection(conn)" in source


def test_pool_defaults_are_sized_for_multiple_streamlit_sessions():
    assert hardening._bounded_int("MISSING_POOL_SETTING", 10, 1, 50) == 10


def test_checkout_resets_psycopg_transaction_to_read_write():
    connection = _FakeConnection()

    result = hardening._prepare_postgres_connection(connection)

    assert result is connection
    assert connection.rollback_calls == 1
    assert connection.session_calls == [
        {"readonly": False, "autocommit": False}
    ]


def test_checkout_fallback_clears_readonly_and_autocommit_flags():
    connection = _FallbackConnection()

    result = hardening._prepare_postgres_connection(connection)

    assert result is connection
    assert connection.rollback_calls == 1
    assert connection.readonly is False
    assert connection.autocommit is False


def test_checkout_rejects_closed_connection():
    connection = _FakeConnection()
    connection.closed = 1

    try:
        hardening._prepare_postgres_connection(connection)
    except RuntimeError as exc:
        assert "closed connection" in str(exc)
    else:
        raise AssertionError("closed pooled connections must be rejected")
