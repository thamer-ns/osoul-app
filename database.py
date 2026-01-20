import psycopg2
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# === إعداد الاتصال المحسن ===
@contextmanager
def get_db():
    # التحقق من وجود الرابط
    if "DATABASE_URL" not in st.secrets:
        st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات في Secrets.")
        yield None
        return

    conn = None
    try:
        # محاولة الاتصال
        conn = psycopg2.connect(st.secrets["DATABASE_URL"])
        yield conn
    except psycopg2.Error as e:
        # عرض الخطأ بشكل جميل بدلاً من انهيار التطبيق
        error_msg = str(e)
        if "password authentication failed" in error_msg:
            st.error("❌ كلمة المرور في Streamlit Secrets غير صحيحة. يرجى التأكد منها.")
        elif "Circuit breaker open" in error_msg:
            st.warning("⏳ النظام في فترة حماية مؤقتة (Circuit Breaker). يرجى الانتظار 15 دقيقة قبل المحاولة مجدداً.")
        else:
            st.error(f"خطأ في الاتصال: {e}")
        yield None
    finally:
        if conn:
            conn.close()

# === دوال مساعدة ===
def execute_query(query, params=()):
    # تحويل علامة الاستفهام إلى الصيغة المدعومة في بوستجريس
    fixed_query = query.replace('?', '%s')
    with get_db() as conn:
        if conn: # تأكد أن الاتصال نجح قبل التنفيذ
            try:
                with conn.cursor() as cur:
                    cur.execute(fixed_query, params)
                    conn.commit()
            except Exception as e:
                st.error(f"خطأ في التنفيذ: {e}")

def fetch_table(table_name):
    with get_db() as conn:
        if conn:
            try:
                return pd.read_sql(f"SELECT * FROM {table_name}", conn)
            except:
                return pd.DataFrame()
    return pd.DataFrame()

# === تهيئة الجداول ===
def init_db():
    tables_commands = [
        """CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password TEXT, created_at TIMESTAMP DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS Trades (
            id SERIAL PRIMARY KEY, symbol TEXT, company_name TEXT, sector TEXT, asset_type TEXT DEFAULT 'Stock',
            date TEXT, quantity FLOAT, entry_price FLOAT, strategy TEXT, status TEXT,
            exit_date TEXT, exit_price FLOAT, current_price FLOAT, prev_close FLOAT, 
            year_high FLOAT, year_low FLOAT, dividend_yield FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date TEXT, amount FLOAT, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date TEXT, amount FLOAT, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date TEXT, symbol TEXT, company_name TEXT, amount FLOAT)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol TEXT PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS SectorTargets (sector TEXT PRIMARY KEY, target_percentage FLOAT)""",
        """CREATE TABLE IF NOT EXISTS FinancialStatements (
            id SERIAL PRIMARY KEY, symbol TEXT, period_type TEXT, date TEXT, revenue FLOAT, net_income FLOAT, 
            gross_profit FLOAT, operating_income FLOAT, total_assets FLOAT, total_liabilities FLOAT, total_equity FLOAT, 
            operating_cash_flow FLOAT, free_cash_flow FLOAT, eps FLOAT, source TEXT, 
            UNIQUE(symbol, period_type, date)
        )""",
        """CREATE TABLE IF NOT EXISTS InvestmentThesis (
            symbol TEXT PRIMARY KEY, thesis_text TEXT, target_price FLOAT, recommendation TEXT, last_updated TEXT
        )"""
    ]
    
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for cmd in tables_commands:
                    try: cur.execute(cmd)
                    except: pass
                conn.commit()

# === دوال المستخدمين ===
def db_create_user(username, password):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        execute_query("INSERT INTO Users (username, password) VALUES (?, ?)", (username, hashed))
        return True
    except:
        return False

def db_verify_user(username, password):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (username,))
                user = cur.fetchone()
                if user:
                    stored_hash = user[0]
                    return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
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
    return True

def clean_database_duplicates():
    pass
