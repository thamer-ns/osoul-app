"""Database helpers for AI engine outputs.

These functions store and retrieve *derived* indicator results (features/signals)
so the UI and AI engine can re-use the latest computed results quickly.

Design goals:
- Work on SQLite and Postgres.
- No hard dependency on pandas.
- Never break the main app if DB isn't available.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional


# ============================================================
# Compatibility helpers (used by ai_engine_core.user_rules)
# ============================================================


def _safe_import_db():
    """Return (execute_query, kind) or (None, 'none') if DB isn't available."""
    try:
        from database import execute_query, get_connection, put_connection

        # Probe connection to infer kind without forcing callers to import database.
        conn, kind = get_connection()
        put_connection(conn, kind)
        return execute_query, kind
    except Exception:
        return None, "none"


def _adapt_placeholders(sql: str, kind: str) -> str:
    """Convert %s placeholders to ? for sqlite."""
    if kind == "postgres":
        return sql
    # sqlite uses qmark style
    return sql.replace("%s", "?")


def _try_exec(sql: str, params: tuple = ()) -> bool:
    """Execute a parameterized SQL safely across Postgres/SQLite."""
    try:
        from database import get_connection, put_connection

        conn, kind = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(_adapt_placeholders(sql, kind), params or ())
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            put_connection(conn, kind)
    except Exception:
        return False


def _safe_fetch_table(table_name: str):
    """Fetch a whole table as a pandas DataFrame. Returns None if unavailable."""
    try:
        from database import fetch_table

        df = fetch_table(table_name)
        return df
    except Exception:
        return None


def _ensure_user_rules_table() -> None:
    """Create ai_user_rules table if missing."""
    try:
        from database import get_connection, put_connection

        conn, kind = get_connection()
        try:
            cur = conn.cursor()
            if kind == "postgres":
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_user_rules (
                        id TEXT PRIMARY KEY,
                        created_at TEXT,
                        title TEXT,
                        rule_text TEXT,
                        parsed_json TEXT,
                        enabled INTEGER DEFAULT 1
                    );
                    """
                )
            else:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_user_rules (
                        id TEXT PRIMARY KEY,
                        created_at TEXT,
                        title TEXT,
                        rule_text TEXT,
                        parsed_json TEXT,
                        enabled INTEGER DEFAULT 1
                    );
                    """
                )
            conn.commit()
        finally:
            put_connection(conn, kind)
    except Exception:
        return


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _get_conn():
    # Local import to avoid circular dependencies at import time.
    from database import get_connection

    return get_connection()


def ensure_advanced_indicators_table() -> None:
    """Create storage table if missing."""
    try:
        conn, kind = _get_conn()
        cur = conn.cursor()

        if kind == "postgres":
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

        if kind == "postgres":
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
        if kind == "postgres":
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
