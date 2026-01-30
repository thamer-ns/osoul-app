import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import re

# 1. إعداد الاتصال
try:
    DB_URL = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
except:
    DB_URL = ""

# Whitelist للجداول المسموح قراءتها (أمان)
_ALLOWED_TABLES = {
    "users", "trades", "deposits", "withdrawals", "returnsgrants",
    "watchlist", "investmentthesis", "financialstatements"
}

def _safe_ident(name: str) -> str:
    """حماية بسيطة لمنع SQL injection في أسماء الجداول/الأعمدة."""
    name = (name or "").strip()
    if not re.match(r"^[A-Za-z0-9_]+$", name):
        return ""
    return name

@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        return None
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e:
        st.error(f"DB Error: {e}")
        return None

@contextmanager
def get_db():
    pool_obj = get_connection_pool()
    if not pool_obj:
        yield None
        return

    conn = pool_obj.getconn()
    try:
        yield conn
    except Exception as e:
        print(f"DB Connection Error: {e}")
        yield None
    finally:
        if conn:
            pool_obj.putconn(conn)

# 2. تنفيذ الأوامر
def execute_query(query, params=()):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    fixed_query = query.replace('?', '%s')
                    cur.execute(fixed_query, params)
                    conn.commit()
                    return True
            except Exception as e:
                try:
                    conn.rollback()
                except:
                    pass
                print(f"Query Error: {e}")
                return False
    return False

def fetch_table(table_name):
    """
    قراءة الجدول بشكل متوافق:
    - يجرب quoted "Name"
    - ثم يجرب lowercase name
    مع حماية ضد إدخال أسماء غير آمنة.
    """
    with get_db() as conn:
        if conn:
            t = _safe_ident(table_name)
            if not t:
                return pd.DataFrame()

            # 1) حاول quoted (قد يكون موجود لو تم إنشاؤه بعلامات اقتباس)
            try:
                return pd.read_sql(f'SELECT * FROM "{t}"', conn)
            except:
                pass

            # 2) حاول lowercase (الوضع الطبيعي في Postgres)
            low = t.lower()
            if low not in _ALLOWED_TABLES:
                return pd.DataFrame()

            try:
                return pd.read_sql(f"SELECT * FROM {low}", conn)
            except:
                return pd.DataFrame()

    return pd.DataFrame()

# 3. تحديث هيكلية البيانات (Migration)
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
        ("period_type", "VARCHAR(20)")
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for col_name, col_type in columns_to_add:
                    # جرّب على جدول quoted أولاً
                    try:
                        cur.execute(f'ALTER TABLE "FinancialStatements" ADD COLUMN IF NOT EXISTS {col_name} {col_type}')
                    except:
                        conn.rollback()
                        # جرّب على lowercase
                        try:
                            cur.execute(f'ALTER TABLE financialstatements ADD COLUMN IF NOT EXISTS {col_name} {col_type}')
                        except:
                            conn.rollback()
            conn.commit()

def init_db():
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
        )"""
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(t)
            conn.commit()

    migrate_financial_schema()

# 4. المصادقة
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except Exception as e:
        print(f"Create User Error: {e}")
        return False

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                    res = cur.fetchone()
                    if res and res[0]:
                        return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
            except Exception as e:
                print(f"Verify User Error: {e}")
    return False

# تشغيل التهيئة
if DB_URL:
    try:
        init_db()
    except Exception as e:
        print(f"Init DB Failed: {e}")
