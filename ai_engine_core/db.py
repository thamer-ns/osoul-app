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


def execute_query(query: str, params: Optional[Tuple[Any, ...]] = None) -> bool:
    """Compatibility wrapper re-exporting database.execute_query.

    Returns False when the database layer is unavailable.
    """
    fn, _ = _safe_import_db()
    if not fn:
        return False
    kind = _get_db_kind()
    q = _adapt_sql_placeholders(query, kind)
    try:
        return bool(fn(q, tuple(params or ())))
    except Exception:
        return False


def fetch_table(table: str, limit: Optional[int] = None):
    """Compatibility wrapper re-exporting database.fetch_table.

    Some AI modules import ``fetch_table`` directly from ``ai_engine_core.db``.
    Keep this stable even if underlying storage is unavailable.
    """
    _, fn = _safe_import_db()
    if not fn:
        return []

    lim: Optional[int]
    try:
        lim = None if limit is None else max(0, int(limit))
    except Exception:
        lim = None

    def _apply_limit(rows):
        if lim is None:
            return rows
        if hasattr(rows, "head"):
            try:
                return rows.head(lim)
            except Exception:
                pass
        try:
            return rows[:lim]
        except Exception:
            pass
        try:
            return list(rows)[:lim]
        except Exception:
            return rows

    try:
        rows = fn(str(table), limit=lim)
        return _apply_limit(rows)
    except TypeError:
        rows = fn(str(table))
        return _apply_limit(rows)
    except Exception:
        return []


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
    """Create ai_signals + ai_weights tables used by logging/learning (compat)."""
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

    # Best-effort schema upgrades used by newer logging/reporting code
    try:
        _try_add_column("ai_signals", "market_trend", "TEXT", "TEXT")
        _try_add_column("ai_signals", "regime", "TEXT", "TEXT")
        _try_add_column("ai_signals", "ctx_key", "TEXT", "TEXT")
        _try_add_column("ai_signals", "horizons_json", "TEXT", "JSONB")
    except Exception:
        pass

    try:
        _ensure_ai_outcomes_table()
        _try_add_column("ai_outcomes", "max_dd_pct", "REAL", "DOUBLE PRECISION")
        _try_add_column("ai_outcomes", "max_ru_pct", "REAL", "DOUBLE PRECISION")
        _try_add_column("ai_outcomes", "exit_price", "REAL", "DOUBLE PRECISION")
        _try_add_column("ai_outcomes", "exit_at", "TEXT", "TIMESTAMP")
        _try_add_column("ai_outcomes", "context_json", "TEXT", "JSONB")
    except Exception:
        pass


def _ensure_ai_advanced_table() -> None:
    """Create ai_advanced_indicators table if missing (store advanced indicators)."""
    kind = _get_db_kind()
    if (kind or "").lower() == "postgres":
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_advanced_indicators (
                id TEXT PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                computed_at TIMESTAMP,
                indicators_json JSONB
            );
            """
        )
    else:
        _try_exec(
            """
            CREATE TABLE IF NOT EXISTS ai_advanced_indicators (
                id TEXT PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                computed_at TEXT,
                indicators_json TEXT
            );
            """
        )


def ensure_tables() -> None:
    _ensure_user_rules_table()
    _ensure_ai_advanced_table()
    _ensure_ai_outcomes_table()

    # Optional evolving columns
    _try_add_column("ai_outcomes", "max_dd_pct", "REAL", "DOUBLE PRECISION")
    _try_add_column("ai_outcomes", "max_ru_pct", "REAL", "DOUBLE PRECISION")
    _try_add_column("ai_outcomes", "exit_price", "REAL", "DOUBLE PRECISION")
    _try_add_column("ai_outcomes", "exit_at", "TEXT", "TIMESTAMP")
    _try_add_column("ai_outcomes", "context_json", "TEXT", "JSONB")


def upsert_user_rule(rule_id: str, title: str, rule_text: str, parsed_json: Dict[str, Any], enabled: int = 1) -> bool:
    ensure_tables()
    kind = _get_db_kind()
    payload = json.dumps(parsed_json, ensure_ascii=False)
    now = _now_iso()

    if (kind or "").lower() == "postgres":
        q = """
        INSERT INTO ai_user_rules (id, created_at, title, rule_text, parsed_json, enabled)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            rule_text = EXCLUDED.rule_text,
            parsed_json = EXCLUDED.parsed_json,
            enabled = EXCLUDED.enabled;
        """
        return _try_exec(q, (rule_id, now, title, rule_text, payload, enabled))

    q = """
    INSERT OR REPLACE INTO ai_user_rules (id, created_at, title, rule_text, parsed_json, enabled)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    return _try_exec(q, (rule_id, now, title, rule_text, payload, enabled))


def list_user_rules() -> list:
    ensure_tables()
    rows = _safe_fetch_table("ai_user_rules")
    if rows is None:
        return []
    try:
        # If pandas DF
        if hasattr(rows, "to_dict"):
            return rows.to_dict("records")  # type: ignore
    except Exception:
        pass
    try:
        return list(rows)
    except Exception:
        return []


def delete_user_rule(rule_id: str) -> bool:
    ensure_tables()
    kind = _get_db_kind()
    if (kind or "").lower() == "postgres":
        return _try_exec("DELETE FROM ai_user_rules WHERE id=%s;", (rule_id,))
    return _try_exec("DELETE FROM ai_user_rules WHERE id=?;", (rule_id,))


def save_advanced_indicators(symbol: str, timeframe: str, indicators: Dict[str, Any]) -> bool:
    ensure_tables()
    kind = _get_db_kind()
    now = _now_iso()
    doc = json.dumps(indicators, ensure_ascii=False)
    key = f"{symbol}:{timeframe}"

    if (kind or "").lower() == "postgres":
        q = """
        INSERT INTO ai_advanced_indicators (id, symbol, timeframe, computed_at, indicators_json)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (id) DO UPDATE SET
            computed_at = EXCLUDED.computed_at,
            indicators_json = EXCLUDED.indicators_json;
        """
        return _try_exec(q, (key, symbol, timeframe, now, doc))

    q = """
    INSERT OR REPLACE INTO ai_advanced_indicators (id, symbol, timeframe, computed_at, indicators_json)
    VALUES (?, ?, ?, ?, ?);
    """
    return _try_exec(q, (key, symbol, timeframe, now, doc))


def load_advanced_indicators(symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
    ensure_tables()
    rows = _safe_fetch_table("ai_advanced_indicators")
    if rows is None:
        return None

    target_id = f"{symbol}:{timeframe}"
    rec = None

    try:
        # pandas DataFrame
        if hasattr(rows, "loc"):
            df = rows  # type: ignore
            try:
                hit = df[df["id"] == target_id]
                if len(hit) > 0:
                    rec = hit.iloc[-1].to_dict()
            except Exception:
                pass
        else:
            for r in rows:
                try:
                    if isinstance(r, dict) and r.get("id") == target_id:
                        rec = r
                except Exception:
                    continue
    except Exception:
        rec = None

    if not rec:
        return None

    raw = rec.get("indicators_json")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


def save_outcome(
    signal_id: str,
    horizon_days: int,
    return_pct: float,
    win: int,
    exit_reason: str = "",
    hit_tp: int = 0,
    hit_sl: int = 0,
    max_dd_pct: Optional[float] = None,
    max_ru_pct: Optional[float] = None,
    exit_price: Optional[float] = None,
    exit_at: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Store a realized outcome for a signal/horizon."""
    ensure_tables()
    kind = _get_db_kind()
    now = _now_iso()
    outcome_id = f"{signal_id}:{horizon_days}"

    ctx_json = json.dumps(context or {}, ensure_ascii=False)
    if (kind or "").lower() == "postgres":
        q = """
        INSERT INTO ai_outcomes (
            id, signal_id, horizon_days, return_pct, win, exit_reason,
            hit_tp, hit_sl, max_dd_pct, max_ru_pct, exit_price, exit_at, context_json
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (id) DO UPDATE SET
            return_pct = EXCLUDED.return_pct,
            win = EXCLUDED.win,
            exit_reason = EXCLUDED.exit_reason,
            hit_tp = EXCLUDED.hit_tp,
            hit_sl = EXCLUDED.hit_sl,
            max_dd_pct = EXCLUDED.max_dd_pct,
            max_ru_pct = EXCLUDED.max_ru_pct,
            exit_price = EXCLUDED.exit_price,
            exit_at = EXCLUDED.exit_at,
            context_json = EXCLUDED.context_json;
        """
        return _try_exec(
            q,
            (
                outcome_id,
                signal_id,
                int(horizon_days),
                float(return_pct),
                int(win),
                str(exit_reason or ""),
                int(hit_tp),
                int(hit_sl),
                None if max_dd_pct is None else float(max_dd_pct),
                None if max_ru_pct is None else float(max_ru_pct),
                None if exit_price is None else float(exit_price),
                exit_at or now,
                ctx_json,
            ),
        )

    q = """
    INSERT OR REPLACE INTO ai_outcomes (
        id, signal_id, horizon_days, return_pct, win, exit_reason,
        hit_tp, hit_sl, max_dd_pct, max_ru_pct, exit_price, exit_at, context_json
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);
    """
    return _try_exec(
        q,
        (
            outcome_id,
            signal_id,
            int(horizon_days),
            float(return_pct),
            int(win),
            str(exit_reason or ""),
            int(hit_tp),
            int(hit_sl),
            None if max_dd_pct is None else float(max_dd_pct),
            None if max_ru_pct is None else float(max_ru_pct),
            None if exit_price is None else float(exit_price),
            exit_at or now,
            ctx_json,
        ),
    )


def list_outcomes(signal_id: Optional[str] = None) -> list:
    """Return outcomes. If DB fetch_table can't filter, we filter in Python."""
    ensure_tables()
    rows = _safe_fetch_table("ai_outcomes")
    if rows is None:
        return []
    out = []
    try:
        if hasattr(rows, "to_dict"):
            out = rows.to_dict("records")  # type: ignore
        else:
            out = list(rows)
    except Exception:
        try:
            out = list(rows)
        except Exception:
            return []

    if not signal_id:
        return out
    filtered = []
    for r in out:
        try:
            if isinstance(r, dict) and r.get("signal_id") == signal_id:
                filtered.append(r)
        except Exception:
            pass
    return filtered
