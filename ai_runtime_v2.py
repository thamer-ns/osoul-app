"""Runtime hardening for AI reports and personal user rules."""
from __future__ import annotations

import contextvars
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from database import fetch_df, get_connection, put_connection
from tenant_db import current_username
from technical_indicators.advanced_v2 import confirmed_frame

_AI_CONTEXT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "osoul_ai_confirmed_timeframe",
    default=None,
)
_INSTALLED = False


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _interval(timeframe: str) -> str:
    value = str(timeframe or "1D").strip().upper()
    return {
        "1H": "1h",
        "60M": "1h",
        "30M": "30m",
        "15M": "15m",
        "5M": "5m",
        "1W": "1wk",
        "1M": "1mo",
    }.get(value, "1d")


def _ensure_rules_table() -> bool:
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_user_rules_v2 (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    title TEXT,
                    rule_text TEXT NOT NULL,
                    parsed_json JSONB,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_user_rules_v2_user "
                "ON ai_user_rules_v2(user_id, enabled, created_at)"
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_user_rules_v2 (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    title TEXT,
                    rule_text TEXT NOT NULL,
                    parsed_json TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_user_rules_v2_user "
                "ON ai_user_rules_v2(user_id, enabled, created_at)"
            )
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


def save_user_rule_v2(rule_text: str, title: str | None = None, enabled: int = 1):
    from ai_engine_core.user_rules import _parse_user_rule

    username = current_username()
    text = str(rule_text or "").strip()
    if not text:
        return {"ok": False, "reason": "empty"}
    parsed = _parse_user_rule(text)
    payload = json.dumps(parsed, ensure_ascii=False)
    rule_id = str(uuid.uuid4())
    conn, kind = get_connection()
    try:
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                INSERT INTO ai_user_rules_v2
                    (id,user_id,created_at,title,rule_text,parsed_json,enabled)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
                """,
                (rule_id, username, _now(), title or "قاعدة مستخدم", text, payload, int(enabled)),
            )
        else:
            cur.execute(
                """
                INSERT INTO ai_user_rules_v2
                    (id,user_id,created_at,title,rule_text,parsed_json,enabled)
                VALUES (?,?,?,?,?,?,?)
                """,
                (rule_id, username, _now(), title or "قاعدة مستخدم", text, payload, int(enabled)),
            )
        conn.commit()
        return {"ok": True, "parsed": parsed, "id": rule_id}
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "reason": type(exc).__name__}
    finally:
        put_connection(conn, kind)


def load_user_rules_v2(enabled_only: bool = True, max_rows: int = 50):
    from ai_engine_core.user_rules import _parse_user_rule

    username = current_username(required=False)
    if not username:
        return []
    query = "SELECT * FROM ai_user_rules_v2 WHERE user_id=%s"
    params: tuple[Any, ...] = (username,)
    if enabled_only:
        query += " AND enabled=1"
    query += " ORDER BY created_at DESC LIMIT %s"
    params += (max(1, int(max_rows)),)
    frame = fetch_df(query, params)
    if frame is None or frame.empty:
        return []
    rules = []
    for _, row in frame.iterrows():
        raw = row.get("parsed_json")
        try:
            parsed = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        except Exception:
            parsed = _parse_user_rule(str(row.get("rule_text") or ""))
        rules.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or "قاعدة مستخدم",
                "rule_text": row.get("rule_text") or "",
                "parsed": parsed,
            }
        )
    return rules


def _install_confirmed_history_context() -> None:
    import market_data

    if getattr(market_data.get_chart_history, "_osoul_context_guard", False):
        return
    original = market_data.get_chart_history

    def guarded_history(*args, **kwargs):
        frame = original(*args, **kwargs)
        timeframe = _AI_CONTEXT.get()
        if not timeframe or frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            return frame
        confirmed, excluded = confirmed_frame(frame, _interval(timeframe))
        try:
            confirmed.attrs.update(frame.attrs)
            lineage = dict(confirmed.attrs.get("data_lineage") or {})
            lineage["confirmation_rule"] = "closed_candle"
            lineage["live_bar_excluded"] = bool(excluded)
            confirmed.attrs["data_lineage"] = lineage
        except Exception:
            pass
        return confirmed

    guarded_history._osoul_context_guard = True  # type: ignore[attr-defined]
    guarded_history._osoul_original = original  # type: ignore[attr-defined]
    market_data.get_chart_history = guarded_history


def _wrap_report_function(original):
    if getattr(original, "_osoul_confirmed_report", False):
        return original

    def generate_confirmed_report(symbol, timeframe="1D", *args, **kwargs):
        token = _AI_CONTEXT.set(str(timeframe or "1D"))
        try:
            report = original(symbol, timeframe=timeframe, *args, **kwargs)
        finally:
            _AI_CONTEXT.reset(token)
        if isinstance(report, dict):
            meta = report.get("engine_meta")
            if not isinstance(meta, dict):
                meta = {}
                report["engine_meta"] = meta
            meta["confirmation_rule"] = "closed_candle"
            report["confirmation_rule"] = "closed_candle"
        return report

    generate_confirmed_report._osoul_confirmed_report = True  # type: ignore[attr-defined]
    return generate_confirmed_report


def install_ai_runtime_guards() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True
    if not _ensure_rules_table():
        return False

    import ai_engine_core.user_rules as rules

    rules.save_user_rule = save_user_rule_v2
    rules.load_user_rules = load_user_rules_v2
    _install_confirmed_history_context()

    import ai_engine_core.reporting as reporting

    reporting.load_user_rules = load_user_rules_v2
    reporting.generate_ai_report = _wrap_report_function(reporting.generate_ai_report)

    try:
        import ai_engine

        ai_engine.generate_ai_report = reporting.generate_ai_report
        ai_engine.save_user_rule = save_user_rule_v2
        ai_engine.load_user_rules = load_user_rules_v2
    except Exception:
        pass

    _INSTALLED = True
    return True
