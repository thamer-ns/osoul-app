import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import re

# 1) إعداد الاتصال
try:
    DB_URL = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
except Exception:
    DB_URL = ""

@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        return None
    try:
        return psycopg2.pool.SimpleConnectionPool(
            1, 20, dsn=DB_URL, sslmode="require"
        )
    except Exception as e:
        st.error(f"DB Error: {e}")
        return None

@contextmanager
def get_db():
    """
    ✅ إصلاح مهم:
    - contextmanager لازم يعمل yield مرة واحدة فقط.
    - لو صار exception داخل البلوك: rollback ثم نعيد رفع الخطأ.
    """
    pool_obj = get_connection_pool()
    if not pool_obj:
        yield None
        return

    conn = pool_obj.getconn()
    try:
        yield conn
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"DB Connection/Block Error: {e}")
        raise
    finally:
        try:
            pool_obj.putconn(conn)
        except Exception:
            pass


# =========================================================
# ✅ SQL Table Name Normalizer (Case-Safe for Postgres)
# =========================================================
KNOWN_TABLES = [
    # Core
    "Users", "Trades", "Deposits", "Withdrawals", "ReturnsGrants",
    "Watchlist", "InvestmentThesis", "FinancialStatements",

    # AI / Lab (إضافة مفيدة)
    "ai_signals", "ai_weights", "ai_user_rules",
    "lab_runs", "lab_trades", "lab_equity",
    "ai_decisions",
]

def normalize_sql_tables(query: str) -> str:
    """
    يحول أسماء الجداول المعروفة إلى lowercase إذا كانت غير مقتبسة "Quoted".
    لا يلمس أي اسم بين " " حتى لا يكسر الاستعلامات المقتبسة.
    """
    if not query:
        return query

    fixed = query
    for t in KNOWN_TABLES:
        fixed = re.sub(rf'(?<!")\b{re.escape(t)}\b(?!")', str(t).lower(), fixed)
    return fixed

def _fix_placeholders(query: str) -> str:
    """
    دعم استعلامات ? (لو في كود ثاني يستخدم SQLite style).
    """
    if not query:
        return query
    return query.replace("?", "%s")


# =========================================================
# 2) Execute / Fetch
# =========================================================
def execute_query(query, params=()):
    with get_db() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                fixed_query = normalize_sql_tables(query)
                fixed_query = _fix_placeholders(fixed_query)
                cur.execute(fixed_query, params)
                conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"Query Error: {e}")
            return False

def fetch_table(table_name):
    """
    يحاول:
    1) SELECT * FROM "table_name" (لو المستخدم مرر اسم مقتبس/حساس)
    2) SELECT * FROM table_name.lower()
    3) SELECT * FROM normalized(table_name)
    """
    with get_db() as conn:
        if not conn:
            return pd.DataFrame()
        try:
            # 1) Quoted exactly as passed (قد ينجح لو الجدول فعلاً مقتبس)
            return pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
        except Exception:
            pass

        try:
            # 2) Lowercase unquoted (الأكثر شيوعاً عندك)
            return pd.read_sql(f"SELECT * FROM {str(table_name).lower()}", conn)
        except Exception:
            pass

        try:
            # 3) Normalize using the same logic as execute_query
            t = normalize_sql_tables(str(table_name)).strip()
            t = t.replace('"', "")
            return pd.read_sql(f"SELECT * FROM {t}", conn)
        except Exception:
            return pd.DataFrame()


# =========================================================
# 3) Migration / Init
# =========================================================
def migrate_financial_schema():
    """
    ✅ إصلاح:
    - كان يحاول ALTER على "FinancialStatements" (غلط لأن الجدول منشأ lowercase).
    - الآن يشتغل على financialstatements مباشرة.
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
        # Postgres supports IF NOT EXISTS
        execute_query(
            f"ALTER TABLE financialstatements ADD COLUMN IF NOT EXISTS {col_name} {col_type}",
            ()
        )

def init_db():
    """
    ✅ الأفضل توحيد كل الجداول lowercase بدون Quotes.
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
                    cur.execute(t)
            conn.commit()

    migrate_financial_schema()


# =========================================================
# 4) Auth
# =========================================================
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        # normalize_sql_tables سيحوّل Users -> users
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except Exception as e:
        print(f"Create User Error: {e}")
        return False

def db_verify_user(u, p):
    """
    ✅ إصلاح:
    - كان يستخدم Users (capital) مباشرة بدون normalize => يفشل.
    - الآن يستخدم users lowercase صراحة.
    """
    with get_db() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res and res[0]:
                    return bcrypt.checkpw(p.encode("utf-8"), res[0].encode("utf-8"))
        except Exception as e:
            print(f"Verify User Error: {e}")
            return False
    return False


# =========================================================
# 5) Healthcheck
# =========================================================
def db_healthcheck():
    """
    تشخيص سريع: يعرض معلومات الاتصال + عداد سجلات الجداول + كشف ازدواج الجداول.
    لا يغير أي بيانات.
    """
    info = {"connected": False, "db": {}, "counts": {}, "dup_tables": []}

    with get_db() as conn:
        if not conn:
            return info

        info["connected"] = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port();")
                dbname, user, host, port = cur.fetchone()
                info["db"] = {"database": dbname, "user": user, "host": host, "port": port}

                tables = ["users","trades","deposits","withdrawals","returnsgrants","watchlist","investmentthesis","financialstatements"]
                for t in tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {t};")
                        info["counts"][t] = cur.fetchone()[0]
                    except Exception:
                        info["counts"][t] = None

                cur.execute("""
                    SELECT tablename FROM pg_tables
                    WHERE schemaname='public'
                    AND tablename IN ('trades','Trades','deposits','Deposits','financialstatements','FinancialStatements');
                """)
                found = [r[0] for r in cur.fetchall()]
                pairs = [("Trades","trades"),("Deposits","deposits"),("FinancialStatements","financialstatements")]
                for a, b in pairs:
                    if a in found and b in found:
                        info["dup_tables"].append((a, b))

        except Exception as e:
            info["db"]["error"] = str(e)

    return info

# ✅ IMPORTANT: لا تشغل init_db هنا (سيتم تشغيلها من app.py فقط)