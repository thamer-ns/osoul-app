import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# 1. إعداد الاتصال
try:
    DB_URL = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
except:
    DB_URL = ""

@st.cache_resource
def get_connection_pool():
    if not DB_URL: return None
    try: return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e: st.error(f"DB Error: {e}"); return None

@contextmanager
def get_db():
    pool_obj = get_connection_pool()
    if not pool_obj: yield None; return
    conn = pool_obj.getconn()
    try: yield conn
    except Exception as e: print(f"DB Log: {e}"); yield None
    finally: if conn: pool_obj.putconn(conn)

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
                conn.rollback()
                print(f"Query Error: {e}")
                return False
    return False

def fetch_table(table_name):
    with get_db() as conn:
        if conn:
            try:
                return pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
            except:
                try: return pd.read_sql(f'SELECT * FROM {table_name.lower()}', conn)
                except: pass
    return pd.DataFrame()

# 3. الترحيل (Migration) - حل مشكلة الأعمدة المفقودة
def migrate_financial_schema():
    """ضمان وجود كل الأعمدة المطلوبة في جدول القوائم المالية"""
    required_cols = [
        ("total_assets", "DOUBLE PRECISION"),
        ("total_liabilities", "DOUBLE PRECISION"),
        ("total_equity", "DOUBLE PRECISION"),
        ("operating_cash_flow", "DOUBLE PRECISION"),
        ("current_assets", "DOUBLE PRECISION"),
        ("current_liabilities", "DOUBLE PRECISION"),
        ("long_term_debt", "DOUBLE PRECISION"),
        ("source", "VARCHAR(20)")
    ]
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for col, dtype in required_cols:
                    try:
                        cur.execute(f'ALTER TABLE "FinancialStatements" ADD COLUMN IF NOT EXISTS {col} {dtype}')
                    except: conn.rollback()
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
        """CREATE TABLE IF NOT EXISTS FinancialStatements (
            symbol VARCHAR(20), date DATE, revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, 
            period_type VARCHAR(20) DEFAULT 'Annual', source VARCHAR(20) DEFAULT 'Auto',
            PRIMARY KEY(symbol, date, period_type)
        )""",
        "CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)"
    ]
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: cur.execute(t)
            conn.commit()
    migrate_financial_schema()

# 4. المصادقة (إصلاح SyntaxError السابق)
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except: return False

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                    res = cur.fetchone()
                    if res and res[0]:
                        return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
            except: pass
    return False

if DB_URL: init_db()
