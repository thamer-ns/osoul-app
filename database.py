import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# محاولة قراءة الرابط
try: DB_URL = st.secrets["postgres"]["url"]
except: DB_URL = ""

@st.cache_resource
def get_connection_pool():
    if not DB_URL: return None
    try: return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except: return None

@contextmanager
def get_db():
    pool = get_connection_pool()
    if not pool: yield None; return
    conn = None
    try: conn = pool.getconn(); yield conn
    except: yield None
    finally:
        if conn: pool.putconn(conn)

def execute_query(query, params=()):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur: cur.execute(query, params); conn.commit(); return True
            except: conn.rollback(); return False
    return False

def fetch_table(table_name):
    # تعريف الجداول
    SCHEMAS = {
        'Trades': ['id', 'symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'strategy', 'status'],
        'Deposits': ['id', 'date', 'amount', 'note'],
        'Withdrawals': ['id', 'date', 'amount', 'note'],
        'ReturnsGrants': ['id', 'date', 'symbol', 'company_name', 'amount', 'note'],
        'FinancialStatements': ['symbol', 'date', 'revenue', 'net_income']
    }
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
                df.columns = df.columns.str.lower()
                # إصلاح البيانات الناقصة لتجنب KeyError
                if table_name == 'Trades' and 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
                if table_name in ['Deposits', 'Withdrawals'] and 'amount' not in df.columns: df['amount'] = 0.0
                return df
            except: pass
    return pd.DataFrame(columns=SCHEMAS.get(table_name, []))

# دوال المستخدمين والتهيئة
def db_create_user(u, p):
    h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res: return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
    return False

def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT)",
        "CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20))",
        "CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION)",
        "CREATE TABLE IF NOT EXISTS FinancialStatements (symbol VARCHAR(20), date DATE, revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, PRIMARY KEY (symbol, date))"
    ]
    # الترقية التلقائية (Migrations)
    migrations = [
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS asset_type VARCHAR(20) DEFAULT 'Stock'",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS company_name TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS sector TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS strategy VARCHAR(20)",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS status VARCHAR(10) DEFAULT 'Open'",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS quantity DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS entry_price DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS exit_price DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS current_price DOUBLE PRECISION DEFAULT 0"
    ]
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: 
                    try: cur.execute(t)
                    except: pass
                for m in migrations:
                    try: cur.execute(m); conn.commit()
                    except: conn.rollback()
                conn.commit()
