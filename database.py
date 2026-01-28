import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

# 1. إعداد رابط قاعدة البيانات
try:
    # محاولة قراءة الرابط المباشر
    DB_URL = st.secrets["DATABASE_URL"]
except:
    try:
        # محاولة قراءة الرابط من قسم postgres
        DB_URL = st.secrets["postgres"]["url"]
    except:
        DB_URL = ""

# 2. إنشاء مسبح الاتصالات (Connection Pool)
@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        return None
    try:
        # إنشاء مسبح اتصالات لزيادة الأداء
        return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e:
        st.error(f"خطأ الاتصال بقاعدة البيانات: {e}")
        return None

# 3. إدارة الاتصال (Context Manager)
@contextmanager
def get_db():
    pool_obj = get_connection_pool()
    if not pool_obj:
        yield None
        return
    
    conn = None
    try:
        conn = pool_obj.getconn()
        yield conn
    except Exception as e:
        # طباعة الخطأ في الكونسول للمطور
        print(f"DB Connection Error: {e}")
        yield None
    finally:
        if conn:
            pool_obj.putconn(conn)

# 4. تنفيذ الأوامر (INSERT, UPDATE, DELETE)
def execute_query(query, params=()):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    # تحويل ؟ إلى %s في حال تم تمرير كود SQLite بالخطأ
                    fixed_query = query.replace('?', '%s')
                    cur.execute(fixed_query, params)
                    conn.commit()
                    return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error executing query: {e}")
                return False
    return False

# 5. جلب البيانات (SELECT)
def fetch_table(table_name):
    with get_db() as conn:
        if conn:
            try:
                # PostgreSQL حساس لحالة الأحرف في أسماء الجداول إذا كانت بين علامات تنصيص
                q = f'SELECT * FROM "{table_name}"'
                return pd.read_sql(q, conn)
            except:
                try:
                    # محاولة الحروف الصغيرة في حال فشل الأولى
                    return pd.read_sql(f'SELECT * FROM {table_name.lower()}', conn)
                except Exception as e:
                    print(f"Fetch table error: {e}")
                    pass
    return pd.DataFrame()

# 6. تهيئة الجداول
def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)",
        """CREATE TABLE IF NOT EXISTS Trades (
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
        "CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY, target_price DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS FinancialStatements (symbol VARCHAR(20), date DATE, revenue DOUBLE PRECISION, net_income DOUBLE PRECISION, total_equity DOUBLE PRECISION, period_type VARCHAR(20), source VARCHAR(20), PRIMARY KEY(symbol, date, period_type))",
        "CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)"
    ]
    
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    for t in tables:
                        cur.execute(t)
                    conn.commit()
            except Exception as e:
                conn.rollback()
                st.error(f"Init DB Error: {e}")

# 7. وظائف المستخدمين (Authentication)
def db_create_user(u, p):
    # تشفير كلمة المرور
    h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                    res = cur.fetchone()
                    if res and res[0]:
                        # التحقق من كلمة المرور
                        return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
            except Exception as e:
                print(f"Auth Error: {e}")
    return False

# تشغيل التهيئة عند الاستيراد
if DB_URL:
    init_db()
