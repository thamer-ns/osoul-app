import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# === محاولة جلب رابط قاعدة البيانات ===
def get_db_url():
    # المحاولة 1: من ملف secrets.toml
    try:
        return st.secrets["postgres"]["url"]
    except:
        pass
    
    # المحاولة 2: (للاختبار المحلي فقط - ضع الرابط الكامل هنا إذا فشل الملف السري)
    # استبدل "رمزي الخاص" بكلمة المرور الحقيقية
    return "postgresql://postgres.uxcdbjqnbphlzftpfajm:رمزي الخاص@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres?sslmode=require"

DB_URL = get_db_url()

@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        st.error("❌ لم يتم العثور على رابط قاعدة البيانات (DATABASE_URL). تأكد من ملف secrets.toml")
        return None
    try:
        # إنشاء مسبح اتصالات
        return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL)
    except Exception as e:
        st.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None

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
    except Exception as e:
        st.error(f"خطأ أثناء جلب الاتصال: {e}")
        yield None
    finally:
        if conn:
            pool.putconn(conn)

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
                st.error(f"خطأ في تنفيذ الأمر: {e}")
                return False
    return False

def fetch_table(table_name):
    # تعريف الجداول والأعمدة المتوقعة لتجنب الأخطاء
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
                
                # معالجة الجدول الفارغ
                if df.empty and table_name in SCHEMAS:
                    return pd.DataFrame(columns=[c.lower() for c in SCHEMAS[table_name]])
                
                # ضمان وجود عمود amount للجداول المالية
                if table_name in ['Deposits', 'Withdrawals', 'ReturnsGrants'] and 'amount' not in df.columns:
                     df['amount'] = 0.0
                     
                return df
            except Exception as e:
                # لا تظهر الخطأ للمستخدم العادي، فقط سجل
                pass
                
    # إرجاع جدول فارغ في حال الفشل
    return pd.DataFrame(columns=[c.lower() for c in SCHEMAS.get(table_name, [])])

# === إدارة المستخدمين ===
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
    # إنشاء الجداول الأساسية
    tables = [
        "CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)",
        "CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT, asset_type VARCHAR(20) DEFAULT 'Stock', date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION, strategy VARCHAR(20), status VARCHAR(10), exit_date DATE, exit_price DOUBLE PRECISION, current_price DOUBLE PRECISION, prev_close DOUBLE PRECISION, year_high DOUBLE PRECISION, year_low DOUBLE PRECISION, dividend_yield DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS Documents (id SERIAL PRIMARY KEY, trade_id INTEGER, file_name TEXT, file_data BYTEA, upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ]
    
    # تحديثات الأعمدة (Migrations) لضمان عدم فقدان البيانات القديمة
    migrations = [
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS asset_type VARCHAR(20) DEFAULT 'Stock'",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS sector TEXT",
        "ALTER TABLE Trades ADD COLUMN IF NOT EXISTS company_name TEXT",
        "ALTER TABLE ReturnsGrants ADD COLUMN IF NOT EXISTS symbol VARCHAR(20)",
        "ALTER TABLE ReturnsGrants ADD COLUMN IF NOT EXISTS company_name TEXT"
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                # 1. إنشاء الجداول
                for t in tables: 
                    try: cur.execute(t)
                    except: pass
                
                # 2. تطبيق التحديثات
                for m in migrations:
                    try: 
                        cur.execute(m)
                        conn.commit()
                    except: 
                        conn.rollback()
                
                conn.commit()

def clear_all_data(): pass
