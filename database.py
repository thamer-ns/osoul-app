import sqlite3
import pandas as pd
from contextlib import contextmanager
from config import DB_PATH
import logging
import bcrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    try: yield conn
    finally: conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password TEXT, created_at TEXT)")
        
        # الجدول المحدث: أضفنا asset_type
        conn.execute('''CREATE TABLE IF NOT EXISTS Trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            symbol TEXT, 
            company_name TEXT, 
            sector TEXT, 
            asset_type TEXT DEFAULT 'Stock',
            date TEXT, 
            quantity REAL, 
            entry_price REAL, 
            strategy TEXT, 
            status TEXT, 
            exit_date TEXT, 
            exit_price REAL, 
            current_price REAL, 
            prev_close REAL, 
            year_high REAL, 
            year_low REAL,
            dividend_yield REAL
        )''')
        
        conn.execute("CREATE TABLE IF NOT EXISTS Deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, amount REAL, note TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS Withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, amount REAL, note TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ReturnsGrants (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, symbol TEXT, company_name TEXT, amount REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS Watchlist (symbol TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS SectorTargets (sector TEXT PRIMARY KEY, target_percentage REAL)")
        
        # ترحيل البيانات القديمة (Migration)
        try: conn.execute("ALTER TABLE Trades ADD COLUMN asset_type TEXT DEFAULT 'Stock'")
        except: pass
        try: conn.execute("ALTER TABLE Trades ADD COLUMN dividend_yield REAL")
        except: pass
        
        updates = [("ReturnsGrants", "amount", "REAL"), ("ReturnsGrants", "company_name", "TEXT"), ("Deposits", "note", "TEXT"), ("Withdrawals", "note", "TEXT")]
        for tbl, col, typ in updates:
            try: conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
            except: pass

def db_create_user(username, password):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO Users (username, password, created_at) VALUES (?, ?, datetime('now'))", (username, hashed))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def db_verify_user(username, password):
    with get_db() as conn:
        user = conn.execute("SELECT password FROM Users WHERE username = ?", (username,)).fetchone()
        if user:
            stored_hash = user['password']
            try:
                if isinstance(stored_hash, str): stored_hash = stored_hash.encode('utf-8')
                return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
            except ValueError:
                return str(user['password']) == password
        return False

def fetch_table(table_name):
    with get_db() as conn:
        try: return pd.read_sql(f"SELECT * FROM {table_name}", conn)
        except: return pd.DataFrame()

def execute_query(query, params=()):
    with get_db() as conn:
        conn.execute(query, params)
        conn.commit()
