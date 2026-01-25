import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

@st.cache_resource
def get_connection_pool():
    # استخدام الرابط المباشر الذي زودتني به
    DB_URL = "postgresql://postgres.uxcdbjqnbphlzftpfajm:Tm1074844687@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
    except Exception as e:
        logger.error(f"Pool Error: {e}")
        return None

@contextmanager
def get_db():
    pool = get_connection_pool()
    if not pool: yield None; return
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception: yield None
    finally:
        if conn: pool.putconn(conn)

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
                st.error(f"Database Error: {e}")
                return False
    return False

def fetch_table(table_name):
    with get_db() as conn:
        if conn:
            try: return pd.read_sql(f"SELECT * FROM {table_name}", conn)
            except: pass
    return pd.DataFrame()

def init_db():
    queries = [
        """CREATE TABLE IF NOT EXISTS Users (username VARCHAR(50) PRIMARY KEY, password TEXT)""",
        """CREATE TABLE IF NOT EXISTS Trades (id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT, asset_type VARCHAR(20), date DATE, quantity NUMERIC, entry_price NUMERIC, strategy VARCHAR(20), status VARCHAR(10), exit_date DATE, exit_price NUMERIC, current_price NUMERIC, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Deposits (id SERIAL PRIMARY KEY, date DATE, amount NUMERIC, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS Withdrawals (id SERIAL PRIMARY KEY, date DATE, amount NUMERIC, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS ReturnsGrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount NUMERIC)""",
        """CREATE TABLE IF NOT EXISTS Watchlist (symbol VARCHAR(20) PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS SectorTargets (sector VARCHAR(50) PRIMARY KEY, target_percentage NUMERIC)""",
        """CREATE TABLE IF NOT EXISTS InvestmentThesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price NUMERIC, recommendation VARCHAR(20))"""
    ]
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for q in queries: 
                    try: cur.execute(q)
                    except: pass
                conn.commit()

def clear_all_data():
    tables = ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'SectorTargets', 'InvestmentThesis']
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables: 
                    try: cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE;")
                    except: pass
                conn.commit()
