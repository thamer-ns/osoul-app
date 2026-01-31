# database.py
import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import re
import config  # استيراد ملف الإعدادات

# =========================================================
# 1. إعداد الاتصال (Connection Setup)
# =========================================================

@st.cache_resource
def get_connection_pool():
    """
    إنشاء مسبح اتصالات (Connection Pool) لمرة واحدة فقط.
    """
    if not config.DB_CONNECTION_URL:
        st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات في secrets.toml")
        return None
    
    try:
        return psycopg2.pool.SimpleConnectionPool(
            minconn=1, 
            maxconn=20, 
            dsn=config.DB_CONNECTION_URL, 
            sslmode="require"
        )
    except Exception as e:
        st.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")
        return None

@contextmanager
def get_db():
    """
    Context Manager آمن للتعامل مع الاتصال.
    يضمن إرجاع الاتصال للـ Pool سواء نجحت العملية أو فشلت.
    """
    pool_obj = get_connection_pool()
    if not pool_obj:
        yield None
        return

    conn = pool_obj.getconn()
    try:
        yield conn
        # التغييرات (commit) يجب أن تتم داخل الدالة التي تستدعي get_db أو هنا
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        pool_obj.putconn(conn)

# =========================================================
# 2. أدوات مساعدة (Utilities)
# =========================================================
KNOWN_TABLES = [
    "users", "trades", "deposits", "withdrawals", "returnsgrants",
    "watchlist", "investmentthesis", "financialstatements",
    "ai_signals", "ai_weights", "lab_runs"
]

def normalize_sql_tables(query: str) -> str:
    """تحويل أسماء الجداول المعروفة إلى lowercase لضمان توافق Postgres"""
    if not query: return query
    fixed = query
    for t in KNOWN_TABLES:
        # استبدال الاسم إذا لم يكن محاطاً بعلامات تنصيص
        fixed = re.sub(rf'(?<!")\b{re.escape(t)}\b(?!")', t.lower(), fixed, flags=re.IGNORECASE)
    return fixed

def execute_query(query, params=()):
    """تنفيذ أمر SQL (INSERT, UPDATE, DELETE)"""
    with get_db() as conn:
        if not conn: return False
        try:
            with conn.cursor() as cur:
                fixed_query = normalize_sql_tables(query).replace("?", "%s")
                cur.execute(fixed_query, params)
                conn.commit()
            return True
        except Exception as e:
            st.toast(f"خطأ قاعدة بيانات: {e}", icon="❌") # استخدام toast أفضل من print
            return False

def fetch_table(table_name):
    """جلب جدول كامل كـ DataFrame"""
    with get_db() as conn:
        if not conn: return pd.DataFrame()
        
        # تنظيف اسم الجدول
        clean_name = str(table_name).lower().strip().replace('"', '')
        
        try:
            return pd.read_sql(f'SELECT * FROM "{clean_name}"', conn)
        except Exception:
            return pd.DataFrame()

# =========================================================
# 3. إنشاء الجداول (Initialization)
# =========================================================
def init_db():
    """إنشاء الجداول إذا لم تكن موجودة"""
    tables = [
        """CREATE TABLE IF NOT EXISTS users (
            username VARCHAR(50) PRIMARY KEY, 
            password TEXT, 
            email TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY, 
            symbol VARCHAR(20), 
            company_name TEXT, 
            sector TEXT,
            asset_type VARCHAR(20), 
            date DATE, 
            quantity DOUBLE PRECISION, 
            entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION DEFAULT 0, 
            current_price DOUBLE PRECISION DEFAULT 0,
            strategy VARCHAR(20), 
            status VARCHAR(10) DEFAULT 'Open', 
            exit_date DATE, 
            notes TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS financialstatements (
            symbol VARCHAR(20), 
            date DATE,
            revenue DOUBLE PRECISION, 
            net_income DOUBLE PRECISION,
            total_assets DOUBLE PRECISION,
            total_liabilities DOUBLE PRECISION,
            operating_cash_flow DOUBLE PRECISION,
            period_type VARCHAR(20) DEFAULT 'Annual',
            source VARCHAR(20) DEFAULT 'Auto',
            PRIMARY KEY(symbol, date, period_type)
        )""",
         # يمكن إضافة باقي الجداول هنا
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(t)
            conn.commit()

# =========================================================
# 4. المصادقة (Authentication)
# =========================================================
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return execute_query("INSERT INTO users (username, password) VALUES (%s, %s)", (u, h))
    except Exception as e:
        print(f"Error creating user: {e}")
        return False

def db_verify_user(u, p):
    with get_db() as conn:
        if not conn: return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res and res[0]:
                    return bcrypt.checkpw(p.encode("utf-8"), res[0].encode("utf-8"))
        except Exception:
            return False
    return False

# =========================================================
# ملاحظة: تم اختصار دوال الـ Healthcheck و Migration 
# للحفاظ على نظافة الكود، لكن يمكنك إضافتها إذا كنت تحتاجها للصيانة.
# =========================================================
