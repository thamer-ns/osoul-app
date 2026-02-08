from osoli_logging import log_exception
# database.py

# NOTE: psycopg2 قد لا يكون متاحًا في بعض البيئات.
# لا نريد أن ينهار التطبيق بالكامل بسبب ذلك؛ لذلك نجعل الاستيراد مرنًا.
try:
    import psycopg2  # type: ignore
    from psycopg2 import pool  # type: ignore
except ModuleNotFoundError:
    psycopg2 = None  # type: ignore
    pool = None  # type: ignore

import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import re
import os
import sqlite3
import config  # ربط ملف الإعدادات
from osoli_logging import get_logger, log_exception


# =========================================================
# 1) إعداد الاتصال (Connection Setup)
# =========================================================
_DB_MODE = "postgres"  # or "sqlite"
_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "osoul_local.db")


@st.cache_resource
def get_connection_pool():
    """Return a Postgres connection pool if DATABASE_URL exists.

    Streamlit Cloud deployments sometimes run without Secrets/Env configured.
    In that case we **fallback to SQLite** so the app stays usable (login, watchlist,
    basic trades) instead of crashing.
    """

    global _DB_MODE

    # Try DATABASE_URL from config/env.
    db_url = getattr(config, "DB_CONNECTION_URL", None)
    if not db_url and hasattr(config, "get_db_url"):
        try:
            db_url = config.get_db_url()
        except Exception:
            db_url = None

    # If missing -> SQLite fallback (no error, just warning once).
    if not db_url:
        _DB_MODE = "sqlite"
        st.warning("⚠️ لا يوجد DATABASE_URL — تم استخدام SQLite محليًا (osoul_local.db) تلقائيًا.")
        return None

    # If psycopg2 missing -> SQLite fallback.
    if psycopg2 is None or pool is None:
        _DB_MODE = "sqlite"
        st.warning("⚠️ psycopg2 غير متاح — تم استخدام SQLite محليًا (osoul_local.db) تلقائيًا.")
        return None

    try:
        return pool.SimpleConnectionPool(1, 20, db_url)
    except Exception as e:
        st.error(f"❌ فشل إنشاء Connection Pool: {e}")
        return None


@contextmanager
def get_db():
    """Yield a DB connection.

    - Postgres: from connection pool
    - SQLite fallback: sqlite3 connection
    """
    p = get_connection_pool()

    # SQLite mode
    if p is None and _DB_MODE == "sqlite":
        conn = None
        try:
            conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
            yield conn
        finally:
            try:
                if conn is not None:
                    conn.commit()
                    conn.close()
            except Exception:
                pass
        return

    # Postgres mode
    if p is None:
        yield None
        return

    conn = None
    try:
        conn = p.getconn()
        yield conn
    finally:
        try:
            if conn is not None:
                p.putconn(conn)
        except Exception:
            pass


def _is_safe_identifier(name: str) -> bool:
    """
    Ensure identifier is safe: letters, numbers, underscore only.
    """
    try:
        n = (name or "").strip()
        if not n:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9_]+", n))
    except Exception:
        return False


def normalize_sql_tables(name: str) -> str:
    """
    Normalize input to safe lowercase table names.
    """
    n = (name or "").strip().replace('"', "")
    if not n:
        return ""
    n = re.sub(r"[^A-Za-z0-9_]", "", n)
    return n.lower()


# =========================================================
# 2) واجهة تنفيذ الاستعلامات (Execute helpers)
# =========================================================
def execute_query(query: str, params: tuple = ()):
    """
    Execute a single query (INSERT/UPDATE/DELETE/DDL).
    """
    with get_db() as conn:
        if not conn:
            return False
        try:
            q = query
            p = params

            # SQLite compatibility: convert %s placeholders to ?
            if _DB_MODE == "sqlite":
                q = re.sub(r"%s", "?", q)

            cur = conn.cursor()
            cur.execute(q, p)
            try:
                conn.commit()
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            log_exception(e, "DB execute_query failed", level="ERROR")
            return False


def fetch_table(table_or_query, params: tuple = ()) -> pd.DataFrame:
    """Fetch data as a DataFrame.

    ✅ يدعم حالتين (توافق مع النسخ السليمة):
    1) اسم جدول: fetch_table("trades")
    2) استعلام SQL مع باراميترات: fetch_table("SELECT ... WHERE x=%s", (..,))

    ملاحظة: في SQLite يتم تحويل %s إلى ? تلقائيًا.
    """

    if table_or_query is None:
        return pd.DataFrame()

    q = str(table_or_query).strip()
    if not q:
        return pd.DataFrame()

    q_lower = q.lstrip().lower()
    is_query = (
        " " in q_lower
        or "\n" in q_lower
        or q_lower.startswith("select")
        or q_lower.startswith("with")
        or q_lower.startswith("pragma")
        or q_lower.startswith("show")
    )

    with get_db() as conn:
        if not conn:
            return pd.DataFrame()

        # --- Query mode ---
        if is_query:
            try:
                sql = q
                if _DB_MODE == "sqlite":
                    sql = re.sub(r"%s", "?", sql)
                return pd.read_sql(sql, conn, params=params or ())
            except Exception as e:
                log_exception(e, "fetch_table(query) failed", level="ERROR")
                return pd.DataFrame()

        # --- Table-name mode ---
        name_raw = q.strip().replace('"', "")
        if not name_raw:
            return pd.DataFrame()

        # 0) Ensure safe identifier
        if not _is_safe_identifier(name_raw):
            maybe = normalize_sql_tables(name_raw).strip().replace('"', "")
            if not _is_safe_identifier(maybe):
                return pd.DataFrame()
            name_raw = maybe

        # 1) Try exact
        try:
            return pd.read_sql(f"SELECT * FROM {name_raw}", conn)
        except Exception as e:
            log_exception(e, "Ignored DB read error (exact)", level="DEBUG")

        # 2) Try lowercase
        try:
            return pd.read_sql(f"SELECT * FROM {name_raw.lower()}", conn)
        except Exception as e:
            log_exception(e, "Ignored DB read error (lowercase)", level="DEBUG")

        # 3) Normalize
        try:
            t = normalize_sql_tables(name_raw).strip().replace('"', "")
            if not _is_safe_identifier(t):
                return pd.DataFrame()
            return pd.read_sql(f"SELECT * FROM {t}", conn)
        except Exception:
            return pd.DataFrame()


def get_db_mode() -> str:
    """Return active DB mode: postgres|sqlite."""
    return str(_DB_MODE or "postgres")


# =========================================================
# 3) إصلاح صياغة CREATE TABLE (PRIMARY KEY)
# =========================================================
def _fix_create_table_primary_key_syntax(sql: str) -> str:
    """Fix common Postgres syntax error: `...) PRIMARY KEY (...)` must be inside parentheses.

    Example (bad):
        CREATE TABLE x (a INT) PRIMARY KEY (a)
    Example (fixed):
        CREATE TABLE x (a INT, PRIMARY KEY (a))
    """
    try:
        s = str(sql or "").strip()
        if not s:
            return s
        if not re.match(r"^CREATE\s+TABLE", s, flags=re.IGNORECASE):
            return s

        # If PRIMARY KEY comes after the closing paren, move it inside
        if re.search(r"\)\s*PRIMARY\s+KEY\s*\(", s, flags=re.IGNORECASE):
            s = re.sub(
                r"\)\s*(PRIMARY\s+KEY\s*\([^\)]*\))",
                r", \1)",
                s,
                flags=re.IGNORECASE,
            )
        return s
    except Exception:
        return sql


# =========================================================
# 4) التهيئة والمايجريشن (Init & Schema Migration)
# =========================================================
def migrate_financial_schema():
    """
    إضافة الأعمدة الجديدة لجدول القوائم المالية إذا لم تكن موجودة.
    """
    columns_to_add = [
        ("total_assets", "DOUBLE PRECISION"),
        ("total_liabilities", "DOUBLE PRECISION"),
        ("total_equity", "DOUBLE PRECISION"),
        ("operating_cash_flow", "DOUBLE PRECISION"),
        ("current_assets", "DOUBLE PRECISION"),
        ("current_liabilities", "DOUBLE PRECISION"),
        ("long_term_debt", "DOUBLE PRECISION"),
        ("source", "VARCHAR(20)"),
        ("period_type", "VARCHAR(20)"),
    ]

    for col_name, col_type in columns_to_add:
        execute_query(
            f"ALTER TABLE financialstatements ADD COLUMN IF NOT EXISTS {col_name} {col_type}",
            (),
        )


def migrate_users_schema():
    """
    تأكد أن جدول users يحتوي على schema_name لاستخدامه في multi-schema إن رغبت لاحقًا.
    إذا لم تستخدم schemas متعددة، سيبقى الافتراضي 'public'.
    """
    execute_query("ALTER TABLE users ADD COLUMN IF NOT EXISTS schema_name VARCHAR(64) DEFAULT 'public'", ())
    execute_query("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT", ())


def init_db():
    """
    إنشاء جميع الجداول الأساسية.
    """

    # -----------------------------------------------------
    # SQLite fallback DDL (keeps the app functional without DATABASE_URL)
    # -----------------------------------------------------
    if _DB_MODE == "sqlite":
        sqlite_tables = [
            """CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                email TEXT,
                schema_name TEXT DEFAULT 'public'
            )""",
            """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                company_name TEXT,
                sector TEXT,
                asset_type TEXT,
                date TEXT,
                quantity REAL,
                entry_price REAL,
                exit_price REAL DEFAULT 0,
                current_price REAL DEFAULT 0,
                strategy TEXT,
                status TEXT DEFAULT 'Open',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                quantity REAL,
                avg_price REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS financialstatements (
                symbol TEXT,
                date TEXT,
                period_type TEXT,
                revenue REAL DEFAULT 0,
                net_income REAL DEFAULT 0,
                total_assets REAL DEFAULT 0,
                total_liabilities REAL DEFAULT 0,
                total_equity REAL DEFAULT 0,
                operating_cash_flow REAL DEFAULT 0,
                debt REAL DEFAULT 0,
                current_assets REAL DEFAULT 0,
                current_liabilities REAL DEFAULT 0,
                gross_profit REAL DEFAULT 0,
                operating_income REAL DEFAULT 0,
                interest_expense REAL DEFAULT 0,
                source TEXT DEFAULT 'Unknown',
                raw_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (symbol, date, period_type)
            )""",
        ]

        with get_db() as conn:
            if not conn:
                return False
            try:
                cur = conn.cursor()
                for t in sqlite_tables:
                    cur.execute(t)
                conn.commit()
                return True
            except Exception as e:
                log_exception(e, "SQLite init_db failed", level="ERROR")
                return False

    tables = [
        # ✅ users: lowercase + schema_name داخل الجدول
        "CREATE TABLE IF NOT EXISTS users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT, schema_name VARCHAR(64) DEFAULT 'public')",

        """CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20),
            company_name TEXT,
            sector TEXT,
            asset_type VARCHAR(20),
            date DATE,
            quantity DOUBLE PRECISION,
            entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION DEFAULT 0,
            current_price DOUBLE PRECISION DEFAULT 0,
            strategy VARCHAR(20),
            status VARCHAR(10) DEFAULT 'Open',
            exit_date DATE,
            notes TEXT
        )""",

        "CREATE TABLE IF NOT EXISTS deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS returnsgrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS watchlist (symbol VARCHAR(20) PRIMARY KEY, target_price DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS investmentthesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)",

        # ✅ financialstatements: PRIMARY KEY داخل الأقواس
        """CREATE TABLE IF NOT EXISTS financialstatements (
            symbol VARCHAR(20),
            date DATE,
            revenue DOUBLE PRECISION,
            net_income DOUBLE PRECISION,
            period_type VARCHAR(20) DEFAULT 'Annual',
            source VARCHAR(20) DEFAULT 'Auto',
            PRIMARY KEY(symbol, date, period_type)
        )""",
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(_fix_create_table_primary_key_syntax(t))
            conn.commit()

    # Migrations
    migrate_financial_schema()
    migrate_users_schema()


# =========================================================
# 5) المصادقة والأمان (Auth)
# =========================================================
def db_create_user(u, p, email: str = None):
    """
    Create a user in `users` table (lowercase to avoid Postgres case issues).
    """
    try:
        u = str(u or "").strip()
        if not u:
            return False

        h = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        if email is not None:
            return execute_query(
                "INSERT INTO users (username, password, email) VALUES (%s, %s, %s)",
                (u, h, str(email)),
            )

        return execute_query(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (u, h),
        )
    except Exception as e:
        log_exception(e, "Ignored DB create user error", level="DEBUG")
        return False


def db_check_login(u, p) -> bool:
    """
    Verify username/password against `users`.
    """
    try:
        u = str(u or "").strip()
        if not u:
            return False

        df = fetch_table("users")
        if df.empty or "username" not in df.columns or "password" not in df.columns:
            return False

        row = df[df["username"] == u]
        if row.empty:
            return False

        stored = row.iloc[0]["password"]
        if not stored:
            return False

        return bcrypt.checkpw(p.encode("utf-8"), str(stored).encode("utf-8"))
    except Exception as e:
        log_exception(e, "Ignored DB auth error", level="DEBUG")
        return False


# =========================================================
# 6) Aliases مطلوبة لملف security.py
# =========================================================
def db_verify_user(username: str, password: str) -> bool:
    """
    اسم متوقع داخل security.py
    """
    return db_check_login(username, password)


def db_user_exists(username: str) -> bool:
    """
    اسم متوقع داخل security.py
    """
    try:
        u = str(username or "").strip()
        if not u:
            return False
        df = fetch_table("users")
        if df.empty or "username" not in df.columns:
            return False
        return bool((df["username"] == u).any())
    except Exception as e:
        log_exception(e, "Ignored DB user_exists error", level="DEBUG")
        return False


def db_get_user_schema(username: str) -> str:
    """
    اسم متوقع داخل security.py
    - إن لم يكن لديك schemas متعددة، يرجع 'public'
    - إذا كان users يحتوي schema_name سيقرأه
    """
    try:
        u = str(username or "").strip()
        if not u:
            return "public"

        df = fetch_table("users")
        if df.empty:
            return "public"

        if "schema_name" in df.columns:
            row = df[df["username"] == u]
            if not row.empty:
                v = row.iloc[0].get("schema_name")
                v = str(v).strip() if v is not None else ""
                return v or "public"

        return "public"
    except Exception as e:
        log_exception(e, "Ignored DB get_user_schema error", level="DEBUG")
        return "public"


# =========================================================
# 7) Healthcheck (مطلوب بواسطة views/settings.py)
# =========================================================
def db_healthcheck() -> dict:
    """
    Healthcheck سريع لقاعدة البيانات.
    مطلوب بواسطة views/settings.py
    """
    import time as _time

    started = _time.time()
    out = {
        "ok": False,
        "error": None,
        "database": None,
        "user": None,
        "host": None,
        "port": None,
        "time_ms": None,
    }

    try:
        with get_db() as conn:
            if not conn:
                out["error"] = "No connection pool / DATABASE_URL missing"
                out["time_ms"] = round((_time.time() - started) * 1000, 2)
                return out

            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                _ = cur.fetchone()

                cur.execute("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port();")
                res = cur.fetchone()
                if res:
                    dbname, user, host, port = res
                    out["database"] = dbname
                    out["user"] = user
                    out["host"] = host
                    out["port"] = port

            out["ok"] = True
            out["time_ms"] = round((_time.time() - started) * 1000, 2)
            return out

    except Exception as e:
        try:
            out["error"] = str(e)
            out["time_ms"] = round((_time.time() - started) * 1000, 2)
        except Exception:
            out["error"] = "Unknown error"
        return out


# =========================================================
# 8) تشخيص قاعدة البيانات (Diagnostics)
# =========================================================
def get_db_diagnostics() -> dict:
    info = {
        "ok": False,
        "db": {},
        "counts": {},
        "dup_tables": [],
    }

    with get_db() as conn:
        if not conn:
            info["db"]["error"] = "No connection"
            return info

        try:
            info["ok"] = True
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port();")
                res = cur.fetchone()
                if res:
                    dbname, user, host, port = res
                    info["db"] = {"database": dbname, "user": user, "host": host, "port": port}

                tables = [
                    "users",
                    "trades",
                    "deposits",
                    "withdrawals",
                    "returnsgrants",
                    "watchlist",
                    "investmentthesis",
                    "financialstatements",
                ]
                for t in tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {t};")
                        info["counts"][t] = cur.fetchone()[0]
                    except Exception:
                        info["counts"][t] = None

                # فحص الجداول المكررة (Capital vs Small) إن وُجدت
                cur.execute(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname='public'
                    AND tablename IN ('trades','Trades','deposits','Deposits','financialstatements','FinancialStatements',
                                     'users','Users','watchlist','Watchlist','investmentthesis','InvestmentThesis',
                                     'withdrawals','Withdrawals','returnsgrants','ReturnsGrants');
                    """
                )
                found = [r[0] for r in cur.fetchall()]
                pairs = [
                    ("Users", "users"),
                    ("Trades", "trades"),
                    ("Deposits", "deposits"),
                    ("Withdrawals", "withdrawals"),
                    ("ReturnsGrants", "returnsgrants"),
                    ("Watchlist", "watchlist"),
                    ("InvestmentThesis", "investmentthesis"),
                    ("FinancialStatements", "financialstatements"),
                ]
                for a, b in pairs:
                    if a in found and b in found:
                        info["dup_tables"].append((a, b))

        except Exception as e:
            info["db"]["error"] = str(e)

    return info


# =========================================================
# 9) أدوات إصلاح متقدمة (اختياري)
# =========================================================
def _table_exists(conn, table_name: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM pg_tables
                    WHERE schemaname='public' AND tablename=%s
                );
                """,
                (table_name,),
            )
            return bool(cur.fetchone()[0])
    except Exception:
        return False


def _get_columns(conn, table_name: str):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                ORDER BY ordinal_position;
                """,
                (table_name,),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def _set_sequence_to_max_id(conn, table_lower: str, id_col: str = "id"):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_serial_sequence(%s, %s);", (table_lower, id_col))
            res = cur.fetchone()
            if not res or not res[0]:
                return True
            seq = res[0]

            cur.execute(f"SELECT COALESCE(MAX({id_col}), 0) FROM {table_lower};")
            mx = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT setval(%s, %s, true);", (seq, mx))
        conn.commit()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception as e2:
            log_exception(e2, "Ignored DB cleanup error", level="DEBUG")
        print(f"Sequence Fix Error ({table_lower}): {e}")
        return False


def migrate_fix_case_duplicate_tables(drop_old: bool = False) -> dict:
    """
    إصلاح ازدواج الجداول بسبب حالة الأحرف (Case Sensitivity).
    """
    report = {"ok": False, "actions": [], "errors": []}

    pairs = [
        ("Users", "users"),
        ("Trades", "trades"),
        ("Deposits", "deposits"),
        ("Withdrawals", "withdrawals"),
        ("ReturnsGrants", "returnsgrants"),
        ("Watchlist", "watchlist"),
        ("InvestmentThesis", "investmentthesis"),
        ("FinancialStatements", "financialstatements"),
    ]

    with get_db() as conn:
        if not conn:
            report["errors"].append("No connection")
            return report

        try:
            for old, new in pairs:
                old_exists = _table_exists(conn, old)
                new_exists = _table_exists(conn, new)

                if old_exists and not new_exists:
                    with conn.cursor() as cur:
                        cur.execute(f'ALTER TABLE "{old}" RENAME TO {new};')
                    conn.commit()
                    report["actions"].append(f"renamed {old} -> {new}")

                if old_exists and new_exists and drop_old:
                    with conn.cursor() as cur:
                        cur.execute(f'DROP TABLE IF EXISTS "{old}" CASCADE;')
                    conn.commit()
                    report["actions"].append(f"dropped duplicate {old}")

                cols = _get_columns(conn, new)
                if "id" in cols:
                    _set_sequence_to_max_id(conn, new, "id")

            report["ok"] = True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            report["errors"].append(str(e))

    return report
