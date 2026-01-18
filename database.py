import sqlite3
import pandas as pd
import bcrypt
from contextlib import contextmanager
from config import DB_PATH
import shutil

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try: yield conn
    finally: conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password_hash BLOB, created_at TEXT)")
        conn.execute('''CREATE TABLE IF NOT EXISTS Trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, company_name TEXT, sector TEXT, 
            date TEXT, quantity REAL, entry_price REAL, strategy TEXT, status TEXT, 
            exit_date TEXT, exit_price REAL, current_price REAL, prev_close REAL, 
            year_high REAL, year_low REAL, dividend_yield REAL DEFAULT 0.0)''')
        # إنشاء الجداول الأخرى (Deposits, Withdrawals, ReturnsGrants, Watchlist)
        for tbl in ['Deposits', 'Withdrawals', 'ReturnsGrants']:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {tbl} (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, amount REAL, note TEXT, symbol TEXT, company_name TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS Watchlist (symbol TEXT PRIMARY KEY)")
        
        # التأكد من وجود الأعمدة الجديدة
        try: conn.execute("ALTER TABLE Trades ADD COLUMN dividend_yield REAL DEFAULT 0.0")
        except: pass

def create_user(username, password):
    # تشفير كلمة المرور
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO Users (username, password_hash, created_at) VALUES (?, ?, datetime('now'))", (username, hashed))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username, password):
    with get_db() as conn:
        user = conn.execute("SELECT password_hash FROM Users WHERE username = ?", (username,)).fetchone()
        if user:
            return bcrypt.checkpw(password.encode('utf-8'), user['password_hash'])
    return False

def create_smart_backup():
    # كود النسخ الاحتياطي
    try:
        latest = DB_PATH.parent / "backups/backup_latest.xlsx"
        if latest.exists(): shutil.copy(latest, latest.parent / "backup_previous.xlsx")
        with pd.ExcelWriter(latest, engine='xlsxwriter') as writer:
            with get_db() as conn:
                for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist']:
                    try: pd.read_sql(f"SELECT * FROM {t}", conn).to_excel(writer, sheet_name=t, index=False)
                    except: pass
        return True
    except: return False
