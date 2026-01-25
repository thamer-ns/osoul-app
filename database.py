import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import logging

# إعداد السجلات لتتبع الأخطاء بصمت
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- 🔒 إعداد الاتصال الآمن ---
# يتم جلب الرابط من ملف .streamlit/secrets.toml
# الهيكلة المتوقعة في ملف الأسرار:
# [postgres]
# url = "postgresql://..."

try:
    # محاولة جلب الرابط من الأسرار
    DB_URL = st.secrets["postgres"]["url"]
except Exception as e:
    # في حال لم يتم العثور على الملف أو الرابط، نوقف التنفيذ ونظهر رسالة خطأ واضحة
    st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات في secrets.toml")
    logger.error(f"Secrets Error: {e}")
    DB_URL = ""

# --- إدارة الاتصال (Connection Pooling) ---

@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        return None
    try:
        # إنشاء مسبح اتصالات لزيادة الكفاءة
        return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e:
        st.error(f"فشل الاتصال بقاعدة البيانات: {e}")
        return None

@contextmanager
def get_db():
    """Context Manager للحصول على اتصال وإعادته للمسبح تلقائياً"""
    pool = get_connection_pool()
    if not pool:
        yield None
        return
    
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        yield None
    finally:
        if conn:
            pool.putconn(conn)

# --- دوال تنفيذ الاستعلامات ---

def execute_query(query, params=()):
    """تنفيذ أوامر التعديل (INSERT, UPDATE, DELETE)"""
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Execute Query Error: {e}")
                return False
    return False

def fetch_table(table_name):
    """جلب جدول كامل كـ DataFrame"""
    # قائمة بيضاء للجداول المسموح بها للحماية من SQL Injection
    allowed = ['Users', 'Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'SectorTargets', 'FinancialStatements', 'InvestmentThesis']
    
    if table_name not in allowed:
        logger.warning(f"Attempt directly fetch unauthorized table: {table_name}")
        return pd.DataFrame()
        
    with get_db() as conn:
        if conn:
            try:
                return pd.read_sql(f"SELECT * FROM {table_name}", conn)
            except Exception as e:
                logger.error(f"Fetch Table Error: {e}")
                pass
    return pd.DataFrame()

# --- دوال إدارة المستخدمين (الأمان) ---

def db_create_user(username, password, email=""):
    """إنشاء مستخدم جديد مع تشفير كلمة المرور"""
    try:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return execute_query("INSERT INTO Users (username, password, email) VALUES (%s, %s, %s)", (username, hashed, email))
    except Exception as e:
        logger.error(f"Create User Error: {e}")
        return False

def db_verify_user(username, password):
    """التحقق من صحة تسجيل الدخول"""
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (username,))
                res = cur.fetchone()
                if res:
                    # مقارنة كلمة المرور المدخلة مع المشفرة في القاعدة
                    return bcrypt.checkpw(password.encode('utf-8'), res[0].encode('utf-8'))
    return False

# --- دالة التهيئة الأولية (تشغيل مرة واحدة) ---

def init_db():
    """إنشاء الجداول إذا لم تكن موجودة"""
    tables = [
        """CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)""",
        """CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT, asset_type VARCHAR(20) DEFAULT 'Stock', date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION, strategy VARCHAR(20), status VARCHAR(10), exit_date DATE, exit_price DOUBLE PRECISION, current_price DOUBLE PRECISION, prev_close DOUBLE PRECISION, year_high DOUBLE PRECISION, year_low DOUBLE PRECISION, dividend_yield DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS SectorTargets (sector VARCHAR(50) PRIMARY KEY, target_percentage DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS FinancialStatements (
            symbol VARCHAR(20), period_type VARCHAR(20), date DATE, 
            revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, 
            gross_profit DOUBLE PRECISION, operating_income DOUBLE PRECISION, 
            total_assets DOUBLE PRECISION, total_liabilities DOUBLE PRECISION, 
            total_equity DOUBLE PRECISION, operating_cash_flow DOUBLE PRECISION, 
            free_cash_flow DOUBLE PRECISION, eps DOUBLE PRECISION, source VARCHAR(50),
            PRIMARY KEY (symbol, period_type, date)
        )""",
        """CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    ]
    
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: 
                    try: cur.execute(t)
                    except Exception as e: logger.error(f"Init Table Error: {e}")
                conn.commit()
