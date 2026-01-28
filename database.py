import sqlite3
import pandas as pd
import streamlit as st
import threading

# 🔒 قفل لمنع تضارب الكتابة في Streamlit (Multi-threading)
DB_LOCK = threading.Lock()
DB_NAME = "portfolio.db"

def get_connection():
    """إنشاء اتصال آمن يدعم العمليات المتعددة"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn

def init_db():
    """تهيئة الجداول مع ضمان وجود الأعمدة الضرورية"""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            
            # جدول الصفقات
            c.execute('''
                CREATE TABLE IF NOT EXISTS Trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    company_name TEXT,
                    asset_type TEXT DEFAULT 'Stock',
                    date TEXT,
                    quantity REAL,
                    entry_price REAL,
                    total_cost REAL,
                    current_price REAL,
                    status TEXT DEFAULT 'Open',
                    strategy TEXT,
                    exit_price REAL DEFAULT 0,
                    exit_date TEXT,
                    notes TEXT
                )
            ''')
            
            # الجداول المالية
            c.execute('''CREATE TABLE IF NOT EXISTS Deposits (id INTEGER PRIMARY KEY, date TEXT, amount REAL, note TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS Withdrawals (id INTEGER PRIMARY KEY, date TEXT, amount REAL, note TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS ReturnsGrants (id INTEGER PRIMARY KEY, date TEXT, symbol TEXT, amount REAL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS Watchlist (symbol TEXT PRIMARY KEY, target_price REAL, note TEXT)''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            st.error(f"فشل تهيئة قاعدة البيانات: {e}")

def execute_query(query, params=None):
    """تنفيذ استعلام آمن وتحويل Syntax PostgreSQL إلى SQLite"""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            
            # 🔧 التحويل السحري: %s -> ?
            fixed_query = query.replace('%s', '?')
            
            if params:
                c.execute(fixed_query, params)
            else:
                c.execute(fixed_query)
                
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            st.error(f"خطأ قاعدة البيانات: {e}")
            return False

def fetch_table(table_name):
    """جلب جدول كامل كـ DataFrame"""
    try:
        conn = get_connection()
        # استخدام pandas مباشرة (آمن من SQL Injection لأننا نتحكم بالاسم بالكود)
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# تشغيل التهيئة عند الاستيراد لضمان وجود الجداول
init_db()
