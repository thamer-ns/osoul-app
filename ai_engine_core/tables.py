# ai_engine/tables.py
from .db import _safe_import_db, _try_exec

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
