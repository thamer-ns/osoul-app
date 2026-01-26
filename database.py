import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# 1. جلب رابط قاعدة البيانات بأمان
try:
    if "postgres" in st.secrets:
        DB_URL = st.secrets["postgres"]["url"]
    else:
        DB_URL = ""
except:
    DB_URL = ""

# 2. إعداد مسبح الاتصالات
@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        return None
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

# 3. مدير الاتصال (Context Manager)
@contextmanager
def get_db():
    pool = get_connection_pool()
    if not pool:
        yield None
        return
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception:
        yield None
    finally:
        if conn:
            pool.putconn(conn)

# 4. دوال التنفيذ
def execute_query(query, params=()):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                print(f"Query Error: {e}")
                return False
    return False

def fetch_table(table_name):
    SCHEMAS = {
        'Trades': ['id', 'symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'strategy', 'status'],
        'Deposits': ['id', 'date', 'amount', 'note'],
        'Withdrawals': ['id', 'date', 'amount', 'note'],
        'ReturnsGrants': ['id', 'date', 'symbol', 'company_name', 'amount', 'note'],
        'Watchlist': ['symbol']
    }
    
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
                df.columns = df.columns.str.lower()
                
                # إصلاح الأعمدة المفقودة تلقائياً
                if table_name == 'Trades':
                    if 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
                    if 'exit_price' not in df.columns: df['exit_price'] = 0.0
                    
                if table_name in ['Deposits', 'Withdrawals'] and 'amount' not in df.columns: 
                    df['amount'] = 0.0
                
                return df
            except: pass
            
    # إرجاع جدول فارغ في حال الفشل
    return pd.DataFrame(columns=[c.lower() for c in SCHEMAS.get(table_name, [])])

# 5. إدارة المستخدمين
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except: return False

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res: 
                    return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
    return False

# 6. تهيئة قاعدة البيانات (الدالة التي يبحث عنها app.py)
def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT)",
        "CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20))",
        "CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION)",
        "CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS Documents (id SERIAL PRIMARY KEY, trade_id INTEGER, file_name TEXT, file_data BYTEA, upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ]
    
    migrations = [
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS asset_type VARCHAR(20) DEFAULT 'Stock'",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS company_name TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS sector TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS strategy VARCHAR(20)",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS status VARCHAR(10) DEFAULT 'Open'",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS quantity DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS entry_price DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS exit_price DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS current_price DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS prev_close DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS year_high DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS year_low DOUBLE PRECISION DEFAULT 0",
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
                    except: conn.rollback()
                conn.commit()
