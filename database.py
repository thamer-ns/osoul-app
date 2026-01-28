import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# 1. إعداد الاتصال
try:
    DB_URL = st.secrets["DATABASE_URL"]
except:
    try: DB_URL = st.secrets["postgres"]["url"]
    except: DB_URL = ""

@st.cache_resource
def get_connection_pool():
    if not DB_URL: return None
    try:
        # تقليل الحد الأدنى للاتصالات لتوفير الموارد
        return psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DB_URL, sslmode='require')
    except Exception as e:
        st.error(f"فشل إنشاء مسبح الاتصالات: {e}")
        return None

@contextmanager
def get_db():
    """مدير سياق للحصول على اتصال وإرجاعه للمسبح تلقائياً"""
    pool = get_connection_pool()
    if not pool: 
        yield None
        return
    
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception as e:
        yield None
    finally:
        if conn:
            pool.putconn(conn)

# 2. دوال التنفيذ
def execute_query(query, params=()):
    """تنفيذ استعلام (INSERT, UPDATE, DELETE)"""
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return True
            except Exception as e:
                conn.rollback()
                st.error(f"خطأ في تنفيذ الأمر: {e}")
                return False
    return False

def fetch_table(table_name):
    """جلب جدول كامل كـ DataFrame"""
    with get_db() as conn:
        if conn:
            try:
                # محاولة الاسم كما هو
                q = f'SELECT * FROM "{table_name}"'
                try: 
                    return pd.read_sql(q, conn)
                except: 
                    # محاولة الحروف الصغيرة (للتوافق)
                    conn.rollback()
                    return pd.read_sql(f'SELECT * FROM {table_name.lower()}', conn)
            except Exception:
                pass
    return pd.DataFrame()

# 3. تهيئة وتحديث قاعدة البيانات (Auto-Migration)
def init_db():
    """إنشاء الجداول وإضافة الأعمدة الناقصة تلقائياً - أهم دالة للتحديثات"""
    
    tables = [
        """CREATE TABLE IF NOT EXISTS Users (
            username VARCHAR(50) PRIMARY KEY, 
            password TEXT, 
            email TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS Trades (
            id SERIAL PRIMARY KEY, 
            symbol VARCHAR(20), 
            company_name TEXT, 
            sector TEXT, 
            asset_type VARCHAR(20), 
            date DATE, 
            exit_date DATE,           
            quantity DOUBLE PRECISION, 
            entry_price DOUBLE PRECISION, 
            exit_price DOUBLE PRECISION, 
            current_price DOUBLE PRECISION, 
            strategy VARCHAR(20), 
            status VARCHAR(10)
        )""",
        """CREATE TABLE IF NOT EXISTS Deposits (
            id SERIAL PRIMARY KEY, 
            date DATE, 
            amount DOUBLE PRECISION, 
            note TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (
            id SERIAL PRIMARY KEY, 
            date DATE, 
            amount DOUBLE PRECISION, 
            note TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (
            id SERIAL PRIMARY KEY, 
            date DATE, 
            symbol VARCHAR(20), 
            company_name TEXT, 
            amount DOUBLE PRECISION, 
            note TEXT
        )""",
        "CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS FinancialStatements (symbol VARCHAR(20), date DATE, revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, period_type VARCHAR(20), source VARCHAR(20), PRIMARY KEY(symbol, date, period_type))",
        "CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)"
    ]

    # قائمة الأعمدة التي يجب إضافتها إذا كانت ناقصة (Migration)
    migrations = [
        ("Trades", "exit_date", "DATE"),
        ("Trades", "company_name", "TEXT"),
        ("Trades", "sector", "TEXT"),
        ("FinancialStatements", "revenue", "DOUBLE PRECISION"),
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                # 1. إنشاء الجداول الأساسية
                for t in tables:
                    try: 
                        cur.execute(t)
                        conn.commit()
                    except Exception: 
                        conn.rollback()

                # 2. تحديث الهيكل القديم (Alter Table)
                for table, column, dtype in migrations:
                    try:
                        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS {column} {dtype}')
                        conn.commit()
                    except:
                        conn.rollback()

# 4. إدارة المستخدمين
def db_create_user(u, p):
    h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res: 
                    return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
    return False
