import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# محاولة جلب الرابط من الأسرار
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
    # تعريف الهيكل لمنع الأخطاء إذا كان الجدول فارغاً
    SCHEMAS = {
        'Trades': ['id', 'symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'strategy', 'status', 'prev_close', 'year_high', 'year_low', 'dividend_yield'],
        'Deposits': ['id', 'date', 'amount', 'note'],
        'Withdrawals': ['id', 'date', 'amount', 'note'],
        'ReturnsGrants': ['id', 'date', 'symbol', 'company_name', 'amount', 'note'],
        'Watchlist': ['symbol'],
        'Documents': ['id', 'file_name']
    }
    
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
                df.columns = df.columns.str.lower()
                
                # إصلاح البيانات الناقصة فوراً
                if table_name == 'Trades' and 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
                if table_name in ['Deposits', 'Withdrawals'] and 'amount' not in df.columns: df['amount'] = 0.0
                
                return df
            except: pass
            
    # إرجاع جدول فارغ مهيكل في حال الفشل
    return pd.DataFrame(columns=[c.lower() for c in SCHEMAS.get(table_name, [])])

def db_create_user(username, password, email=""):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    return execute_query("INSERT INTO Users (username, password, email) VALUES (%s, %s, %s)", (username, hashed, email))

def db_verify_user(username, password):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (username,))
                res = cur.fetchone()
                if res: return bcrypt.checkpw(password.encode('utf-8'), res[0].encode('utf-8'))
    return False

def init_db():
    tables = [
        """CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)""",
        """CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT, asset_type VARCHAR(20) DEFAULT 'Stock', date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION, strategy VARCHAR(20), status VARCHAR(10), exit_date DATE, exit_price DOUBLE PRECISION, current_price DOUBLE PRECISION, prev_close DOUBLE PRECISION, year_high DOUBLE PRECISION, year_low DOUBLE PRECISION, dividend_yield DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS Documents (id SERIAL PRIMARY KEY, trade_id INTEGER, file_name TEXT, file_data BYTEA, upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    ]
    
    # === هذا هو الجزء السحري: إضافة الأعمدة الناقصة لقاعدة البيانات القديمة ===
    migrations = [
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS asset_type VARCHAR(20) DEFAULT 'Stock'",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS sector TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS company_name TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS dividend_yield DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE ReturnsGrants ADD COLUMN IF NOT EXISTS symbol VARCHAR(20)",
        "ALTER TABLE ReturnsGrants ADD COLUMN IF NOT EXISTS company_name TEXT"
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: 
                    try: cur.execute(t)
                    except: pass
                for m in migrations:
                    try: cur.execute(m); conn.commit()
                    except: conn.rollback() # تجاهل الخطأ إذا العمود موجود
                conn.commit()

def clear_all_data(): pass
