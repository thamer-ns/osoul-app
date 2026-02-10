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


# ==============================================================
# Advanced Indicators Cache (UI + AI)
# ==============================================================


def ensure_advanced_indicators_table() -> bool:
    """Create a cache table for advanced technical indicators.

    We store the full payload (features/signals/evidence/confidence/errors)
    as JSON to avoid schema churn while keeping retrieval fast.
    """

    ok = _try_exec(
        """
        CREATE TABLE IF NOT EXISTS advanced_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            symbol TEXT,
            interval TEXT,
            payload_json TEXT
        )
        """,
        (),
    )
    # Simple index for latest lookup
    _try_exec(
        """
        CREATE INDEX IF NOT EXISTS idx_advanced_indicators_symbol_interval_created
        ON advanced_indicators(symbol, interval, created_at)
        """,
        (),
    )
    return bool(ok)


def save_advanced_indicators(symbol: str, interval: str, payload: dict) -> bool:
    """Insert a new cache entry."""
    try:
        ensure_advanced_indicators_table()
        created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        payload_json = json.dumps(payload, ensure_ascii=False)
        return bool(
            _try_exec(
                """
                INSERT INTO advanced_indicators (created_at, symbol, interval, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (created_at, symbol, interval, payload_json),
            )
        )
    except Exception:
        return False


def fetch_latest_advanced_indicators(symbol: str, interval: str) -> dict | None:
    """Fetch the latest cached payload for (symbol, interval)."""
    try:
        ensure_advanced_indicators_table()
        rows = fetch_table(
            """
            SELECT payload_json
            FROM advanced_indicators
            WHERE symbol = ? AND interval = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (symbol, interval),
        )
        if not rows:
            return None
        raw = rows[0].get("payload_json") if isinstance(rows[0], dict) else None
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None
