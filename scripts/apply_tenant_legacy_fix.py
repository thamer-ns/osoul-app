"""Apply legacy tenant identity compatibility and regression tests."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tenant_scope.py"
TEST_TENANT = ROOT / "tests" / "test_tenant_legacy_identity.py"
TEST_UI = ROOT / "tests" / "test_ui_theme_v2.py"


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"Start marker not found: {start}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"End marker not found: {end}")
    return text[:start_index] + replacement + text[end_index:]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    identity_table = '''def _ensure_tenant_users_table() -> None:
    """Create a stable tenant identity registry for legacy auth schemas.

    Some early Osoli databases used ``username`` as the only user identity and
    therefore have no ``users.id`` column. Authentication still works on those
    databases, but tenant isolation needs a stable integer key. This registry
    supplies that key without rewriting passwords or changing the auth table.
    """
    if _connection_kind() == "postgres":
        query = """
        CREATE TABLE IF NOT EXISTS tenant_users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    else:
        query = """
        CREATE TABLE IF NOT EXISTS tenant_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    if not _ORIGINAL_EXECUTE_QUERY(query):
        raise RuntimeError("تعذر إنشاء سجل هوية المستخدمين")


'''
    marker = "def _ensure_portfolios_table() -> None:\n"
    if "def _ensure_tenant_users_table()" not in text:
        text = text.replace(marker, identity_table + marker, 1)

    old_schema = '''def _ensure_schema_once() -> None:
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


'''
    new_schema = '''def _ensure_schema_once() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _INSTALL_LOCK:
        if _SCHEMA_READY:
            return
        _ensure_tenant_users_table()
        _ensure_portfolios_table()
        _ensure_scoped_columns()
        _migrate_tenant_symbol_constraints()
        _SCHEMA_READY = True


'''
    if old_schema in text:
        text = text.replace(old_schema, new_schema, 1)
    elif new_schema not in text:
        raise RuntimeError("Schema initialization block changed unexpectedly")

    new_identity_functions = '''def _resolve_user_id(username: str) -> int:
    """Resolve a stable integer identity across new and legacy user tables."""
    normalized = str(username or "").strip()
    if not normalized:
        raise RuntimeError("اسم المستخدم غير متوفر لتهيئة مساحة البيانات")

    columns = _table_columns("users") if _table_exists("users") else set()
    conn, kind = _db.get_connection()
    try:
        cur = conn.cursor()
        placeholder = "%s" if kind == "postgres" else "?"

        # Preserve the original numeric identity whenever the modern schema has it.
        if "id" in columns:
            cur.execute(
                f"SELECT id FROM users WHERE username={placeholder} LIMIT 1",
                (normalized,),
            )
            row = cur.fetchone()
            if row is not None and row[0] is not None:
                resolved = int(row[0])
                if resolved > 0:
                    return resolved

        # Legacy schema fallback: allocate one stable ID per authenticated username.
        if kind == "postgres":
            cur.execute(
                "INSERT INTO tenant_users (username) VALUES (%s) "
                "ON CONFLICT (username) DO NOTHING",
                (normalized,),
            )
            cur.execute(
                "SELECT id FROM tenant_users WHERE username=%s LIMIT 1",
                (normalized,),
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO tenant_users (username) VALUES (?)",
                (normalized,),
            )
            cur.execute(
                "SELECT id FROM tenant_users WHERE username=? LIMIT 1",
                (normalized,),
            )
        row = cur.fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("تعذر تخصيص هوية ثابتة للمستخدم")
        conn.commit()
        return int(row[0])
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise RuntimeError("تعذر تحديد هوية مساحة المستخدم") from exc
    finally:
        _db.put_connection(conn, kind)


def _ensure_default_portfolio(user_id: int) -> int:
    """Return or atomically create the user's default portfolio."""
    conn, kind = _db.get_connection()
    try:
        cur = conn.cursor()
        placeholder = "%s" if kind == "postgres" else "?"
        cur.execute(
            "SELECT id FROM portfolios WHERE user_id="
            f"{placeholder} ORDER BY is_default DESC, id ASC LIMIT 1",
            (int(user_id),),
        )
        row = cur.fetchone()
        if row is not None and row[0] is not None:
            return int(row[0])

        if kind == "postgres":
            cur.execute(
                "INSERT INTO portfolios "
                "(user_id, name, base_currency, is_default) "
                "VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (user_id, name) DO NOTHING",
                (int(user_id), "المحفظة الرئيسية", "SAR", 1),
            )
            cur.execute(
                "SELECT id FROM portfolios WHERE user_id=%s "
                "ORDER BY is_default DESC, id ASC LIMIT 1",
                (int(user_id),),
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO portfolios "
                "(user_id, name, base_currency, is_default) VALUES (?,?,?,?)",
                (int(user_id), "المحفظة الرئيسية", "SAR", 1),
            )
            cur.execute(
                "SELECT id FROM portfolios WHERE user_id=? "
                "ORDER BY is_default DESC, id ASC LIMIT 1",
                (int(user_id),),
            )
        row = cur.fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("تعذر قراءة المحفظة الافتراضية")
        conn.commit()
        return int(row[0])
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise RuntimeError("تعذر إنشاء المحفظة الافتراضية") from exc
    finally:
        _db.put_connection(conn, kind)


'''
    text = replace_between(
        text,
        "def _resolve_user_id(username: str) -> int:\n",
        "def _claim_legacy_rows(ctx: TenantContext) -> None:\n",
        new_identity_functions,
    )
    TARGET.write_text(text, encoding="utf-8")

    TEST_TENANT.write_text(
        '''from __future__ import annotations

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
''',
        encoding="utf-8",
    )

    TEST_UI.write_text(
        '''from __future__ import annotations

from ui_theme_v2 import build_final_ui_css


def test_final_theme_restores_cairo_and_global_rtl():
    css = build_final_ui_css()
    assert "'Cairo'" in css
    assert 'direction: rtl !important' in css
    assert '[data-testid="stSidebar"]' in css
    assert '[data-testid="stHorizontalBlock"]:has(> [data-testid="column"])' in css


def test_final_theme_preserves_material_icon_fonts():
    css = build_final_ui_css()
    assert "font-family: 'Material Icons' !important" in css
    assert "font-family: 'Material Symbols Outlined' !important" in css
    assert "font-family: 'Material Symbols Rounded' !important" in css
''',
        encoding="utf-8",
    )
    print("Legacy tenant compatibility patch applied")


if __name__ == "__main__":
    main()
