import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager

try: DB_URL = st.secrets["postgres"]["url"]
except: DB_URL = ""

@st.cache_resource
def get_connection_pool():
    if not DB_URL: 
        st.error("الرابط غير موجود في secrets.toml")
        return None
    try: return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e:
        st.error(f"فشل الاتصال بالقاعدة: {e}")
        return None

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
            except Exception as e: 
                st.error(f"خطأ تنفيذ: {e}")
                conn.rollback(); return False
    return False

def fetch_table(table_name):
    SCHEMAS = {
        'Trades': ['id', 'symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'strategy', 'status', 'prev_close', 'year_high', 'year_low', 'dividend_yield'],
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
                if table_name == 'Trades' and 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
                if table_name in ['Deposits', 'Withdrawals'] and 'amount' not in df.columns: df['amount'] = 0.0
                return df
            except Exception as e:
                # طباعة الخطأ للمساعدة
                print(f"Error fetching {table_name}: {e}")
    return pd.DataFrame(columns=[c.lower() for c in SCHEMAS.get(table_name, [])])

# باقي دوال المستخدمين والتهيئة كما هي في النسخ السابقة...
def db_create_user(u, p):
    h = bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))

def db_verify_user(u, p):
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM Users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res: return bcrypt.checkpw(p.encode('utf-8'), res[0].encode('utf-8'))
    return False

def init_db():
    # جداول التهيئة (كما كانت)
    pass 

def clear_all_data(): pass
