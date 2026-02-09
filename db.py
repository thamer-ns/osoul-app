# ai_engine_core/db.py

import pandas as pd
from .core import _now_str

def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None

def _try_exec(sql: str, params=()):
    """
    Portable execute:
    - Postgres style placeholders: %s
    - SQLite style placeholders: ?
    نحاول أولاً كما هو، وإذا فشل نجرب استبدال %s بـ ?
    """
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        execute_query(sql, params)
        return True
    except Exception:
        try:
            sql2 = sql.replace("%s", "?")
            execute_query(sql2, params)
            return True
        except Exception:
            return False

def _safe_fetch_table(name: str):
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return None
    try:
        df = fetch_table(name)
        if isinstance(df, pd.DataFrame):
            return df
        return None
    except Exception:
        return None

# ============================================================
# ✅ Cross-DB table schemas (SQLite/Postgres)
# ============================================================

def _ensure_ai_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False

    ok1 = _try_exec(
        """
        CREATE TABLE IF NOT EXISTS ai_signals (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            symbol TEXT,
            sector TEXT,
            timeframe TEXT,
            horizon_days INTEGER DEFAULT 20,
            strategy_name TEXT,
            features_json TEXT,
            exit_features_json TEXT,
            report_json TEXT,
            outcome_return_pct REAL,
            outcome_win INTEGER
        )
        """,
        (),
    )

    ok2 = _try_exec(
        """
        CREATE TABLE IF NOT EXISTS ai_weights (
            key TEXT PRIMARY KEY,
            weight REAL DEFAULT 1.0,
            updated_at TEXT
        )
        """,
        (),
    )

    return bool(ok1 and ok2)

def _ensure_user_rules_table():
    ok = _try_exec(
        """
        CREATE TABLE IF NOT EXISTS ai_user_rules (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            title TEXT,
            rule_text TEXT,
            parsed_json TEXT,
            enabled INTEGER DEFAULT 1
        )
        """,
        (),
    )
    return bool(ok)
