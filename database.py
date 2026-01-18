import sqlite3
import pandas as pd
from contextlib import contextmanager
from config import DB_PATH, BACKUP_DIR
import shutil
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

def fix_dates():
    try:
        with get_db() as conn:
            tables = ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants']
            for table in tables:
                try:
                    df = pd.read_sql(f"SELECT * FROM {table}", conn)
                    if not df.empty and 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                        if 'exit_date' in df.columns:
                            df['exit_date'] = pd.to_datetime(df['exit_date'], errors='coerce').dt.strftime('%Y-%m-%d')
                        conn.execute(f"DELETE FROM {table}")
                        df.to_sql(table, conn, if_exists='append', index=False)
                        conn.commit()
                except: pass
    except: pass

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password TEXT, created_at TEXT)")
        conn.execute('''CREATE TABLE IF NOT EXISTS Trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, company_name TEXT, sector TEXT, 
            date TEXT, quantity REAL, entry_price REAL, strategy TEXT, status TEXT, 
            exit_date TEXT, exit_price REAL, current_price REAL, prev_close REAL, 
            year_high REAL, year_low REAL)''')
        conn.execute("CREATE TABLE IF NOT EXISTS Deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, amount REAL, note TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS Withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, amount REAL, note TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ReturnsGrants (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, symbol TEXT, company_name TEXT, amount REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS Watchlist (symbol TEXT PRIMARY KEY)")
        
        updates = [("ReturnsGrants", "amount", "REAL"), ("ReturnsGrants", "company_name", "TEXT"), ("Deposits", "note", "TEXT"), ("Withdrawals", "note", "TEXT")]
        for tbl, col, typ in updates:
            try: conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
            except: pass
    fix_dates()

def create_user(username, password):
    # تشفير بسيط أو bcrypt حسب الرغبة (هنا نستخدم النص كما في طلبك)
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO Users (username, password, created_at) VALUES (?, ?, datetime('now'))", (username, password))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username, password):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM Users WHERE username = ? AND password = ?", (username, password)).fetchone()
        return user is not None

def create_smart_backup():
    try:
        latest = BACKUP_DIR / "backup_latest.xlsx"
        if latest.exists(): shutil.copy(latest, BACKUP_DIR / "backup_previous.xlsx")
        with pd.ExcelWriter(latest, engine='xlsxwriter') as writer:
            with get_db() as conn:
                for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'Users']:
                    try: pd.read_sql(f"SELECT * FROM {t}", conn).to_excel(writer, sheet_name=t, index=False)
                    except: pass
        return True
    except: return False
