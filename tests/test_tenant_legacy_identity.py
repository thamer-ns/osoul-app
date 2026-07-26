from __future__ import annotations

import sqlite3

import tenant_scope


def _connection_with_legacy_users():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT)")
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('thamer', 'x')")
    conn.execute(
        "CREATE TABLE tenant_users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "username TEXT NOT NULL UNIQUE, "
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE portfolios ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER NOT NULL, name TEXT NOT NULL, "
        "base_currency TEXT NOT NULL DEFAULT 'SAR', "
        "is_default INTEGER NOT NULL DEFAULT 0, "
        "UNIQUE(user_id, name))"
    )
    conn.commit()
    return conn


def test_legacy_username_only_schema_gets_stable_tenant_id(monkeypatch):
    conn = _connection_with_legacy_users()
    monkeypatch.setattr(tenant_scope._db, "get_connection", lambda: (conn, "sqlite"))
    monkeypatch.setattr(tenant_scope._db, "put_connection", lambda *_: None)
    monkeypatch.setattr(tenant_scope, "_table_exists", lambda name: name in {"users", "tenant_users", "portfolios"})
    monkeypatch.setattr(tenant_scope, "_table_columns", lambda name: {"username", "password_hash"} if name == "users" else set())

    first = tenant_scope._resolve_user_id("thamer")
    second = tenant_scope._resolve_user_id("thamer")

    assert first == second
    assert first > 0
    count = conn.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0]
    assert count == 1


def test_modern_user_id_is_preserved(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE)")
    conn.execute("INSERT INTO users (id, username) VALUES (77, 'thamer')")
    conn.commit()
    monkeypatch.setattr(tenant_scope._db, "get_connection", lambda: (conn, "sqlite"))
    monkeypatch.setattr(tenant_scope._db, "put_connection", lambda *_: None)
    monkeypatch.setattr(tenant_scope, "_table_exists", lambda name: name == "users")
    monkeypatch.setattr(tenant_scope, "_table_columns", lambda name: {"id", "username"})

    assert tenant_scope._resolve_user_id("thamer") == 77


def test_default_portfolio_creation_is_idempotent(monkeypatch):
    conn = _connection_with_legacy_users()
    monkeypatch.setattr(tenant_scope._db, "get_connection", lambda: (conn, "sqlite"))
    monkeypatch.setattr(tenant_scope._db, "put_connection", lambda *_: None)

    first = tenant_scope._ensure_default_portfolio(9)
    second = tenant_scope._ensure_default_portfolio(9)

    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM portfolios WHERE user_id=9").fetchone()[0] == 1
