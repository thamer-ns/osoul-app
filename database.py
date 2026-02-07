from osoli_logging import log_exception
# database.py
# NOTE: psycopg2 قد لا يكون متاحًا في بعض البيئات (أو قد تفشل عملية التثبيت).
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
import config  # تم ربط الملف بـ config
from osoli_logging import get_logger, log_exception


# =========================================================
# 1) إعداد الاتصال (Connection Setup)
# =========================================================
@st.cache_resource
def get_connection_pool():
    """
    Connection pool (cached) for Streamlit using PostgreSQL.
    """
    if psycopg2 is None:
        # لا نُسقط التطبيق بسبب Driver مفقود
        st.error("⚠️ مكتبة psycopg2 غير مثبتة. ثبّت psycopg2-binary داخل requirements.txt أو فعّل بيئة Postgres.")
        return None

    db_url = getattr(config, 'DB_CONNECTION_URL', None) or getattr(config, 'get_db_url', lambda: None)()
    if not db_url:
        st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات. ضع DATABASE_URL في Secrets أو Environment Variables")
        return None

    try:
        # إنشاء مسبح اتصالات بحد أدنى 1 وحد أقصى 20
        return pool.SimpleConnectionPool(1, 20, db_url)
    except Exception as e:
        st.error(f"❌ فشل إنشاء Connection Pool: {e}")
        return None


@contextmanager
def get_db():
    """
    Yield a db connection from pool and return it back to pool.
    """
    p = get_connection_pool()
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
    # Lowercase + keep only safe chars/_.
    n = re.sub(r"[^A-Za-z0-9_]", "", n)
    n = n.lower()
    return n


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
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            log_exception(e, "DB execute_query failed", level="ERROR")
            return False


def fetch_table(table_name: str) -> pd.DataFrame:
    """
    Read whole table as DataFrame. Tries:
      1) exact
      2) lowercase
      3) normalized
    """
    name_raw = str(table_name or "").strip()
    if not name_raw:
        return pd.DataFrame()

    with get_db() as conn:
        if not conn:
            return pd.DataFrame()

        # 1) Try exact (safe-ish)
        try:
            t = name_raw.strip().replace('"', "")
            if _is_safe_identifier(t):
                return pd.read_sql(f"SELECT * FROM {t}", conn)
        except Exception as e:
            log_exception(e, "Ignored DB read error (exact)", level="DEBUG")

        # 2) Try lowercase
        try:
            t = name_raw.strip().replace('"', "").lower()
            if _is_safe_identifier(t):
                return pd.read_sql(f"SELECT * FROM {t}", conn)
        except Exception as e:
            log_exception(e, "Ignored DB read error (lowercase)", level="DEBUG")

        # 3) Normalize from list
        try:
            t = normalize_sql_tables(name_raw).strip().replace('"', "")
            if not _is_safe_identifier(t):
                return pd.DataFrame()
            return pd.read_sql(f"SELECT * FROM {t}", conn)
        except Exception:
            return pd.DataFrame()


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
        # Only target CREATE TABLE statements
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


def init_db():
    """
    إنشاء جميع الجداول الأساسية. يتم استخدام lowercase لتفادي مشاكل Postgres.
    """
    tables = [
        "CREATE TABLE IF NOT EXISTS users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)",
        """CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT,
            asset_type VARCHAR(20), date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION DEFAULT 0, current_price DOUBLE PRECISION DEFAULT 0,
            strategy VARCHAR(20), status VARCHAR(10) DEFAULT 'Open', exit_date DATE, notes TEXT
        )""",
        "CREATE TABLE IF NOT EXISTS deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS returnsgrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS watchlist (symbol VARCHAR(20) PRIMARY KEY, target_price DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS investmentthesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)",
        """CREATE TABLE IF NOT EXISTS financialstatements (
            symbol VARCHAR(20), date DATE,
            revenue DOUBLE PRECISION, net_income DOUBLE PRECISION,
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

    migrate_financial_schema()


# =========================================================
# 5) المصادقة والأمان (Auth)
# =========================================================
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except Exception as e:
        log_exception(e, "Ignored DB create user error", level="DEBUG")
        return False


def db_check_login(u, p):
    try:
        df = fetch_table("users")
        if df.empty:
            return False
        row = df[df["username"] == u]
        if row.empty:
            return False
        stored = row.iloc[0]["password"]
        return bcrypt.checkpw(p.encode("utf-8"), stored.encode("utf-8"))
    except Exception as e:
        log_exception(e, "Ignored DB auth error", level="DEBUG")
        return False


# =========================================================
# 6) تشخيص قاعدة البيانات (Diagnostics)
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

                # فحص الجداول المكررة (Capital vs Small)
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
# 7) أدوات الإصلاح المتقدمة (Advanced Migration Helpers)
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


def _get_primary_key_cols(conn, table_name: str) -> list:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass
                AND i.indisprimary;
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
        except Exception as e:
            log_exception(e, "Ignored DB cleanup error", level="DEBUG")
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
                # check existence
                old_exists = _table_exists(conn, old)
                new_exists = _table_exists(conn, new)

                if old_exists and not new_exists:
                    # rename old -> new (lowercase)
                    with conn.cursor() as cur:
                        cur.execute(f'ALTER TABLE "{old}" RENAME TO {new};')
                    conn.commit()
                    report["actions"].append(f"renamed {old} -> {new}")

                if old_exists and new_exists and drop_old:
                    # drop old if duplicate exists
                    with conn.cursor() as cur:
                        cur.execute(f'DROP TABLE IF EXISTS "{old}" CASCADE;')
                    conn.commit()
                    report["actions"].append(f"dropped duplicate {old}")

                # fix sequence if table has serial id
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