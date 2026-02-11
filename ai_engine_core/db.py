"""Database helpers for AI engine outputs.

This module serves two purposes:
1) Store/retrieve derived indicator results (advanced indicators) for UI caching.
2) Provide small compatibility helpers expected by other AI engine modules
   (user rules + learning logs). These helpers are designed to be safe:
   - Work with SQLite and Postgres.
   - Never crash the main app if DB is unavailable.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# ============================================================
# Generic helpers (compat layer)
# ============================================================

def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _safe_import_db():
    """Return (execute_query, fetch_table) from database.py if available."""
    try:
        from database import execute_query, fetch_table  # type: ignore
        return execute_query, fetch_table
    except Exception:
        return None, None


def _get_db_kind() -> str:
    try:
        from database import get_connection, put_connection  # type: ignore

        conn, kind = get_connection()
        try:
            return str(kind or "none")
        finally:
            try:
                put_connection(conn, kind)
            except Exception:
                pass
    except Exception:
        return "none"


def _adapt_sql_placeholders(q: str, kind: str) -> str:
    """Convert %s placeholders to ? for sqlite."""
    if (kind or "").lower() == "postgres":
        return q
    # sqlite
    return q.replace("%s", "?")


def _try_exec(query: str, params: Optional[Tuple[Any, ...]] = None) -> bool:
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    kind = _get_db_kind()
    q = _adapt_sql_placeholders(query, kind)
    try:
        return bool(execute_query(q, tuple(params or ())))
    except Exception:
        return False


def _safe_fetch_table(table: str):
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return None
    try:
        return fetch_table(str(table))
    except Exception:
        return None


def _ensure_user_rules_table() -> None:
    """Create ai_user_rules table if missing."""
    kind = _get_db_kind()
    if (kind or "").lower() == "postgres":
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_user_rules (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP,
                title TEXT,
                rule_text TEXT,
                parsed_json JSONB,
                enabled INTEGER
            );
            """
        )
    else:
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_user_rules (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                title TEXT,
                rule_text TEXT,
                parsed_json TEXT,
                enabled INTEGER
            );
            """
        )


def _try_add_column(table: str, col: str, col_type_sqlite: str, col_type_pg: str):
    """Best-effort add column if missing (SQLite/Postgres)."""
    kind = _get_db_kind()
    if (kind or "").lower() == "postgres":
        _try_exec(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type_pg};')
    else:
        # SQLite has no IF NOT EXISTS for columns; ignore errors
        _try_exec(f'ALTER TABLE {table} ADD COLUMN {col} {col_type_sqlite};')

def _ensure_ai_outcomes_table() -> None:
    """Create ai_outcomes table (multi-horizon + risk outcomes)."""
    kind = _get_db_kind()
    if (kind or "").lower() == "postgres":
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_outcomes (
                id TEXT PRIMARY KEY,
                signal_id TEXT,
                horizon_days INTEGER,
                return_pct DOUBLE PRECISION,
                win INTEGER,
                exit_reason TEXT,
                hit_tp INTEGER,
                hit_sl INTEGER,
                max_dd_pct DOUBLE PRECISION,
                max_ru_pct DOUBLE PRECISION,
                exit_price DOUBLE PRECISION,
                exit_at TIMESTAMP,
                context_json JSONB
            );
            """
        )
    else:
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_outcomes (
                id TEXT PRIMARY KEY,
                signal_id TEXT,
                horizon_days INTEGER,
                return_pct REAL,
                win INTEGER,
                exit_reason TEXT,
                hit_tp INTEGER,
                hit_sl INTEGER,
                max_dd_pct REAL,
                max_ru_pct REAL,
                exit_price REAL,
                exit_at TEXT,
                context_json TEXT
            );
            """
        )
def _ensure_ai_tables() -> None:
    """Create ai_signals + ai_weights tables used by logging/learning."""
    kind = _get_db_kind()
    if (kind or "").lower() == "postgres":
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_signals (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP,
                symbol TEXT,
                sector TEXT,
                timeframe TEXT,
                horizon_days INTEGER,
                strategy_name TEXT,
                features_json JSONB,
                report_json JSONB,
                outcome_return_pct DOUBLE PRECISION,
                outcome_win INTEGER,
                exit_features_json JSONB
            );
            """
        )
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_weights (
                key TEXT PRIMARY KEY,
                weight DOUBLE PRECISION,
                updated_at TIMESTAMP
            );
            """
        )
    else:
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_signals (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                symbol TEXT,
                sector TEXT,
                timeframe TEXT,
                horizon_days INTEGER,
                strategy_name TEXT,
                features_json TEXT,
                report_json TEXT,
                outcome_return_pct REAL,
                outcome_win INTEGER,
                exit_features_json TEXT
            );
            """
        )
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_weights (
                key TEXT PRIMARY KEY,
                weight REAL,
                updated_at TEXT
            );
            """
        )

# ============================================================
    # ✅ Add new columns for context-aware learning (best-effort on existing DBs)
    try:
        _try_add_column("ai_signals", "market_trend", "TEXT", "TEXT")
        _try_add_column("ai_signals", "regime", "TEXT", "TEXT")
        _try_add_column("ai_signals", "ctx_key", "TEXT", "TEXT")
        _try_add_column("ai_signals", "horizons_json", "TEXT", "JSONB")
    except Exception:
        pass

    # ✅ Multi-horizon outcomes table
    try:
        _ensure_ai_outcomes_table()
    except Exception:
        pass
# Advanced indicators storage (optional caching)
# ============================================================

def _get_conn():
    # Local import to avoid circular dependencies at import time.
    from database import get_connection  # type: ignore
    return get_connection()


def ensure_advanced_indicators_table() -> None:
    """Create storage table if missing."""
    try:
        conn, kind = _get_conn()
        cur = conn.cursor()

        if str(kind) == "postgres":
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS advanced_indicators (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    asof TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    confidence DOUBLE PRECISION,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_adv_indicators_symbol_interval_created_at ON advanced_indicators(symbol, interval, created_at DESC);"
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS advanced_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    asof TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    confidence REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_adv_indicators_symbol_interval_created_at ON advanced_indicators(symbol, interval, created_at);"
            )

        conn.commit()
    except Exception:
        # Storage is optional; never fail the app.
        return


def save_advanced_indicators(
    symbol: str,
    interval: str,
    payload: Dict[str, Any],
    confidence: Optional[float] = None,
    asof: Optional[str] = None,
) -> None:
    """Insert one record."""
    ensure_advanced_indicators_table()
    try:
        conn, kind = _get_conn()
        cur = conn.cursor()

        asof = asof or _now_iso()

        if str(kind) == "postgres":
            cur.execute(
                """
                INSERT INTO advanced_indicators(symbol, asof, interval, payload, confidence)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (symbol, asof, interval, json.dumps(payload), confidence),
            )
        else:
            cur.execute(
                """
                INSERT INTO advanced_indicators(symbol, asof, interval, payload, confidence)
                VALUES (?, ?, ?, ?, ?);
                """,
                (symbol, asof, interval, json.dumps(payload, ensure_ascii=False), confidence),
            )

        conn.commit()
    except Exception:
        return


def fetch_latest_advanced_indicators(symbol: str, interval: str) -> Optional[Dict[str, Any]]:
    """Fetch the most recently stored record for (symbol, interval)."""
    ensure_advanced_indicators_table()
    try:
        conn, kind = _get_conn()
        cur = conn.cursor()
        if str(kind) == "postgres":
            cur.execute(
                """
                SELECT payload, confidence, asof, created_at
                FROM advanced_indicators
                WHERE symbol=%s AND interval=%s
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (symbol, interval),
            )
        else:
            cur.execute(
                """
                SELECT payload, confidence, asof, created_at
                FROM advanced_indicators
                WHERE symbol=? AND interval=?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (symbol, interval),
            )
        row = cur.fetchone()
        if not row:
            return None
        payload_raw, confidence, asof, created_at = row
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        return {
            "payload": payload,
            "confidence": confidence,
            "asof": asof,
            "created_at": str(created_at),
        }
    except Exception:
        return None
