import psycopg2
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import logging

# إعداد السجل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@st.cache_resource
def get_connection_pool():
    # التحقق من وجود الرابط
    if "DATABASE_URL" not in st.secrets:
        st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات.")
        return None
    
    db_url = st.secrets["DATABASE_URL"]
    
    try:
        # للمنفذ 6543: نستخدم اتصال مباشر (بدون Pool محلي)
        # لأن Supabase تدير الـ Pool في هذا المنفذ
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        # طباعة الخطأ بوضوح
        st.error(f"❌ خطأ في الاتصال بقاعدة البيانات.")
        st.code(str(e))
        return None

@contextmanager
def get_db():
    # نطلب الاتصال
    conn = get_connection_pool()
    
    # التحقق من أن الاتصال ما زال حياً
    if conn is not None:
        if conn.closed:
             try:
                 # إعادة الاتصال إذا انقطع
                 db_url = st.secrets["DATABASE_URL"]
                 conn = psycopg2.connect(db_url)
             except: conn = None

    if not conn:
        yield None
        return
        
    try:
        yield conn
    except psycopg2.Error as e:
        logger.error(f"DB Error: {e}")
        conn.rollback() # تراجع عند الخطأ
        yield None
    # لا نغلق الاتصال هنا لأننا نستخدم cache_resource

def execute_query(query, params=()):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                print(f"Query Error: {e}")

def fetch_table(table_name):
    allowed = ['Users', 'Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'SectorTargets', 'FinancialStatements', 'InvestmentThesis']
    if table_name not in allowed: return pd.DataFrame()
    
    with get_db() as conn:
        if conn:
            try:
                return pd.read_sql(f"SELECT * FROM {table_name}", conn)
            except Exception as e:
                return pd.DataFrame()
    return pd.DataFrame()

# === دوال التهيئة والمستخدمين (مهمة جداً) ===
def init_db():
    tables = [
        """CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT, created_at TIMESTAMP DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT, asset_type VARCHAR(20) DEFAULT 'Stock', date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION, strategy VARCHAR(20), status VARCHAR(10), exit_date DATE, exit_price DOUBLE PRECISION, current_price DOUBLE PRECISION, prev_close DOUBLE PRECISION, year_high DOUBLE PRECISION, year_low DOUBLE PRECISION, dividend_yield DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS SectorTargets (sector VARCHAR(50) PRIMARY KEY, target_percentage DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS FinancialStatements (id SERIAL PRIMARY KEY, symbol VARCHAR(20), period_type VARCHAR(20), date DATE, revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, gross_profit DOUBLE PRECISION, operating_income DOUBLE PRECISION, total_assets DOUBLE PRECISION, total_liabilities DOUBLE PRECISION, total_equity DOUBLE PRECISION, operating_cash_flow DOUBLE PRECISION, free_cash_flow DOUBLE PRECISION, eps DOUBLE PRECISION, source VARCHAR(50), UNIQUE(symbol, period_type, date))""",
        """CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated TIMESTAMP DEFAULT NOW())"""
    ]
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: 
                    try: cur.execute(t)
                    except: pass
                try: cur.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS email TEXT;")
                except: pass
                conn.commit()

def db_create_user(username, password, email=""):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try: 
        execute_query("INSERT INTO Users (username, password, email) VALUES (%s, %s, %s)", (username, hashed, email))
        return True, "تم"
    except: return False, "خطأ"

def db_verify_user(username, password):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM Users WHERE username = %s", (username,))
                    user = cur.fetchone()
                    if user: return bcrypt.checkpw(password.encode('utf-8'), user[0].encode('utf-8'))
            except: pass
    return False

def clear_all_data():
    tables = ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'SectorTargets', 'FinancialStatements', 'InvestmentThesis']
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables:
                    try: cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE;")
                    except: pass
                conn.commit()
    st.cache_data.clear()

def get_user_details(username):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT email, created_at FROM Users WHERE username = %s", (username,))
                    return cur.fetchone()
            except: pass
    return None
