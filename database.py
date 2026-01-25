import streamlit as st
import psycopg2
from psycopg2 import pool
import pandas as pd
import bcrypt
from contextlib import contextmanager
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- 1. إعداد الاتصال الآمن ---
try:
    DB_URL = st.secrets["postgres"]["url"]
except Exception as e:
    DB_URL = "" 

# --- 2. إدارة الاتصال ---
@st.cache_resource
def get_connection_pool():
    if not DB_URL: return None
    try: return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e: st.error(f"DB Error: {e}"); return None

@contextmanager
def get_db():
    pool = get_connection_pool()
    if not pool: yield None; return
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception as e: logger.error(f"DB Conn Error: {e}"); yield None
    finally:
        if conn: pool.putconn(conn)

# --- 3. الجلب الآمن (هنا كان سبب المشكلة وتم إصلاحه) ---
def fetch_table(table_name):
    # تعريف الأعمدة الافتراضية لمنع KeyError
    STANDARD_COLS = {
        'Trades': ['id', 'symbol', 'company_name', 'sector', 'status', 'strategy', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'market_value', 'total_cost', 'gain', 'dividend_yield'],
        'Deposits': ['id', 'date', 'amount', 'note'],
        'Withdrawals': ['id', 'date', 'amount', 'note'],
        'ReturnsGrants': ['id', 'date', 'amount', 'symbol', 'company_name', 'note'],
        'Watchlist': ['symbol'],
        'SectorTargets': ['sector', 'target_percentage'],
        'InvestmentThesis': ['symbol', 'thesis_text', 'target_price', 'recommendation'],
        'FinancialStatements': ['symbol', 'date', 'revenue', 'net_income'],
        'Documents': ['id', 'trade_id', 'file_name']
    }
    
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
                # الإصلاح: إذا كان الجدول فارغاً، نعيد هيكلاً فارغاً بالأعمدة الصحيحة
                if df.empty and table_name in STANDARD_COLS:
                    return pd.DataFrame(columns=STANDARD_COLS[table_name])
                return df
            except Exception as e:
                logger.error(f"Fetch {table_name} Error: {e}")
                
    # في حال الفشل التام، نرجع جدولاً فارغاً بالأعمدة الافتراضية
    if table_name in STANDARD_COLS:
        return pd.DataFrame(columns=STANDARD_COLS[table_name])
    return pd.DataFrame()

def execute_query(query, params=()):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                return True
            except Exception as e: conn.rollback(); return False
    return False

# --- 4. المستخدمين ---
def db_create_user(username, password, email=""):
    try:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return execute_query("INSERT INTO Users (username, password, email) VALUES (%s, %s, %s)", (username, hashed, email))
    except: return False

def db_verify_user(username, password):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (username,))
                res = cur.fetchone()
                if res: return bcrypt.checkpw(password.encode('utf-8'), res[0].encode('utf-8'))
    return False

# --- 5. التهيئة ---
def init_db():
    tables = [
        """CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)""",
        """CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT, asset_type VARCHAR(20) DEFAULT 'Stock', date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION, strategy VARCHAR(20), status VARCHAR(10), exit_date DATE, exit_price DOUBLE PRECISION, current_price DOUBLE PRECISION, prev_close DOUBLE PRECISION, year_high DOUBLE PRECISION, year_low DOUBLE PRECISION, dividend_yield DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS SectorTargets (sector VARCHAR(50) PRIMARY KEY, target_percentage DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS FinancialStatements (symbol VARCHAR(20), period_type VARCHAR(20), date DATE, revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, gross_profit DOUBLE PRECISION, operating_income DOUBLE PRECISION, total_assets DOUBLE PRECISION, total_liabilities DOUBLE PRECISION, total_equity DOUBLE PRECISION, operating_cash_flow DOUBLE PRECISION, free_cash_flow DOUBLE PRECISION, eps DOUBLE PRECISION, source VARCHAR(50), PRIMARY KEY (symbol, period_type, date))""",
        """CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS Documents (id SERIAL PRIMARY KEY, trade_id INTEGER, file_name TEXT, file_data BYTEA, upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    ]
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: 
                    try: cur.execute(t)
                    except: pass
                conn.commit()
