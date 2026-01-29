import re
import psycopg2
from psycopg2 import pool
from psycopg2 import sql
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# =========================
# 0) قراءة الرابط بأمان
# =========================
def _get_db_url() -> str:
    try:
        url = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
        return (url or "").strip()
    except Exception:
        return ""

DB_URL = _get_db_url()

# أسماء الجداول المسموح بها (حماية + ثبات)
ALLOWED_TABLES = {
    "Users",
    "Trades",
    "Deposits",
    "Withdrawals",
    "ReturnsGrants",
    "Watchlist",
    "InvestmentThesis",
    "FinancialStatements",
}

@st.cache_resource
def get_connection_pool():
    """
    إنشاء Pool مرة واحدة لكل سيرفر/سيشن (حسب Streamlit).
    """
    if not DB_URL:
        return None
    try:
        return psycopg2.pool.SimpleConnectionPool(
            1,
            20,
            dsn=DB_URL,
            sslmode="require",
            connect_timeout=5,
        )
    except Exception as e:
        # لا تعرض تفاصيل حساسة للمستخدم من داخل طبقة DB
        print(f"[DB] Pool Error: {e}")
        return None

@contextmanager
def get_db():
    pool_obj = get_connection_pool()
    if not pool_obj:
        yield None
        return

    conn = None
    try:
        conn = pool_obj.getconn()
        yield conn
    except Exception as e:
        # لا تبلع الاستثناء بصمت
        print(f"[DB] Connection Error: {e}")
        raise
    finally:
        if conn:
            try:
                pool_obj.putconn(conn)
            except Exception as e:
                print(f"[DB] putconn Error: {e}")

def execute_query(query: str, params=()) -> bool:
    """
    تنفيذ INSERT/UPDATE/DELETE بشكل آمن.
    """
    with get_db() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                fixed_query = query.replace("?", "%s")
                cur.execute(fixed_query, params)
            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[DB] Query Error: {e}\nQuery={query}\nParams={params}")
            return False

def fetch_table(table_name: str) -> pd.DataFrame:
    """
    قراءة جدول كامل مع حماية اسم الجدول.
    """
    if table_name not in ALLOWED_TABLES:
        print(f"[DB] Blocked table access: {table_name}")
        return pd.DataFrame()

    with get_db() as conn:
        if not conn:
            return pd.DataFrame()
        try:
            q = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name))
            return pd.read_sql(q, conn)
        except Exception as e:
            print(f"[DB] Read Error ({table_name}): {e}")
            return pd.DataFrame()

def migrate_financial_schema():
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

    with get_db() as conn:
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                for col_name, col_type in columns_to_add:
                    cur.execute(
                        sql.SQL('ALTER TABLE "FinancialStatements" ADD COLUMN IF NOT EXISTS {} {}')
                        .format(sql.Identifier(col_name), sql.SQL(col_type))
                    )
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[DB] Migration Error: {e}")

def init_db():
    """
    تهيئة الجداول. تُستدعى من app.py مرة واحدة.
    """
    if not DB_URL:
        # إذا تبي fallback SQLite هنا نضيفه لاحقًا، حالياً هذا Postgres-only
        print("[DB] No DB_URL found. Skipping init_db.")
        return

    tables = [
        "CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)",
        """CREATE TABLE IF NOT EXISTS Trades (
            id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT,
            asset_type VARCHAR(20), date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION DEFAULT 0, current_price DOUBLE PRECISION DEFAULT 0,
            strategy VARCHAR(20), status VARCHAR(10) DEFAULT 'Open', exit_date DATE, notes TEXT
        )""",
        "CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY, target_price DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)",
        """CREATE TABLE IF NOT EXISTS FinancialStatements (
            symbol VARCHAR(20), date DATE,
            revenue DOUBLE PRECISION, net_income DOUBLE PRECISION,
            period_type VARCHAR(20) DEFAULT 'Annual',
            source VARCHAR(20) DEFAULT 'Auto',
            PRIMARY KEY(symbol, date, period_type)
        )""",
    ]

    with get_db() as conn:
        if not conn:
            raise RuntimeError("DB connection not available")
        try:
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(t)
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[DB] init_db failed: {e}")
            raise

    migrate_financial_schema()

# =========================
# Auth
# =========================
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except Exception as e:
        print(f"[DB] Create User Error: {e}")
        return False

def db_verify_user(u, p):
    with get_db() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res and res[0]:
                    return bcrypt.checkpw(p.encode("utf-8"), res[0].encode("utf-8"))
        except Exception as e:
            print(f"[DB] Verify User Error: {e}")
        return False
