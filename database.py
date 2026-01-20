import psycopg2
from psycopg2 import pool, DatabaseError
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import logging

# إعداد السجلات (Logging) لمراقبة الأخطاء دون عرضها للمستخدم
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# استخدام st.cache_resource لإنشاء Connection Pool مرة واحدة فقط
@st.cache_resource
def get_connection_pool():
    if "DATABASE_URL" not in st.secrets:
        st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات في Secrets.")
        return None
    try:
        # إنشاء مسبح اتصالات (min=1, max=10)
        return psycopg2.pool.SimpleConnectionPool(
            1, 10, 
            dsn=st.secrets["DATABASE_URL"],
            sslmode='require' # أمان إضافي للاتصال
        )
    except Exception as e:
        logger.error(f"Error creating connection pool: {e}")
        return None

@contextmanager
def get_db():
    connection_pool = get_connection_pool()
    if not connection_pool:
        yield None
        return

    conn = None
    try:
        conn = connection_pool.getconn()
        yield conn
    except psycopg2.Error as e:
        logger.error(f"Database connection error: {e}")
        st.warning("⚠️ هناك ضغط مؤقت على قاعدة البيانات، حاول مرة أخرى بعد قليل.")
        yield None
    finally:
        if conn:
            # إعادة الاتصال للمسبح بدلاً من إغلاقه
            connection_pool.putconn(conn)

def execute_query(query, params=()):
    """
    تنفيذ استعلام آمن.
    ملاحظة هامة: يجب استخدام %s كمعامل استبدال في الاستعلامات بدلاً من ?
    """
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
            except psycopg2.Error as e:
                conn.rollback() # تراجع عند الخطأ
                logger.error(f"Query execution error: {e} | Query: {query}")
                # لا نعرض تفاصيل الخطأ للمستخدم لأسباب أمنية
                st.error("حدث خطأ أثناء حفظ البيانات. يرجى المحاولة لاحقاً.")

def fetch_table(table_name):
    """جلب جدول كامل بأمان"""
    # التحقق من اسم الجدول لمنع SQL Injection في اسم الجدول نفسه
    allowed_tables = [
        'Users', 'Trades', 'Deposits', 'Withdrawals', 
        'ReturnsGrants', 'Watchlist', 'SectorTargets', 
        'FinancialStatements', 'InvestmentThesis'
    ]
    if table_name not in allowed_tables:
        logger.warning(f"Attempted access to unauthorized table: {table_name}")
        return pd.DataFrame()

    with get_db() as conn:
        if conn:
            try:
                # استخدام pandas مع الموصل مباشرة
                return pd.read_sql(f"SELECT * FROM {table_name}", conn)
            except Exception as e:
                logger.error(f"Error fetching table {table_name}: {e}")
                return pd.DataFrame()
    return pd.DataFrame()

def init_db():
    """تهيئة الجداول مع أنواع بيانات Postgres الصحيحة"""
    tables_commands = [
        """CREATE TABLE IF NOT EXISTS Users (
            username VARCHAR(50) PRIMARY KEY, 
            password TEXT NOT NULL, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS Trades (
            id SERIAL PRIMARY KEY, 
            symbol VARCHAR(20), 
            company_name VARCHAR(100), 
            sector VARCHAR(50), 
            asset_type VARCHAR(20) DEFAULT 'Stock', 
            date DATE, 
            quantity DOUBLE PRECISION, 
            entry_price DOUBLE PRECISION, 
            strategy VARCHAR(20), 
            status VARCHAR(10), 
            exit_date DATE, 
            exit_price DOUBLE PRECISION, 
            current_price DOUBLE PRECISION, 
            prev_close DOUBLE PRECISION, 
            year_high DOUBLE PRECISION, 
            year_low DOUBLE PRECISION, 
            dividend_yield DOUBLE PRECISION
        )""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name VARCHAR(100), amount DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS SectorTargets (sector VARCHAR(50) PRIMARY KEY, target_percentage DOUBLE PRECISION)""",
        """CREATE TABLE IF NOT EXISTS FinancialStatements (
            id SERIAL PRIMARY KEY, symbol VARCHAR(20), period_type VARCHAR(20), date DATE, 
            revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, gross_profit DOUBLE PRECISION, 
            operating_income DOUBLE PRECISION, total_assets DOUBLE PRECISION, total_liabilities DOUBLE PRECISION, 
            total_equity DOUBLE PRECISION, operating_cash_flow DOUBLE PRECISION, free_cash_flow DOUBLE PRECISION, 
            eps DOUBLE PRECISION, source VARCHAR(50), 
            UNIQUE(symbol, period_type, date)
        )""",
        """CREATE TABLE IF NOT EXISTS InvestmentThesis (
            symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, 
            recommendation VARCHAR(20), last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    ]
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    for cmd in tables_commands:
                        cur.execute(cmd)
                    conn.commit()
            except psycopg2.Error as e:
                logger.error(f"Init DB Error: {e}")

def db_create_user(username, password):
    # التحقق المسبق
    if not username or not password:
        return False, "البيانات ناقصة"
    
    # التحقق من التكرار قبل المحاولة (أو الاعتماد على خطأ المفتاح الأساسي)
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO Users (username, password) VALUES (%s, %s)", (username, hashed))
                    conn.commit()
                return True, "تم الإنشاء بنجاح"
            except psycopg2.IntegrityError:
                conn.rollback()
                return False, "اسم المستخدم موجود مسبقاً"
            except Exception as e:
                conn.rollback()
                logger.error(f"Create user error: {e}")
                return False, "خطأ غير متوقع"
    return False, "فشل الاتصال"

def db_verify_user(username, password):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM Users WHERE username = %s", (username,))
                    user = cur.fetchone()
                    if user:
                        stored_hash = user[0]
                        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
            except Exception as e:
                logger.error(f"Verify user error: {e}")
    return False
