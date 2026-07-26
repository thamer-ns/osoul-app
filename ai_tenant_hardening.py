"""Tenant isolation for user rules, AI reports and learned weights."""
from __future__ import annotations

import threading

_LEARNING_SCOPE_INSTALLED = False
_AI_TABLES_READY = False
_AI_TABLES_LOCK = threading.RLock()


def register_ai_tenant_tables() -> None:
    """Create AI tables once per process before tenant wrappers are installed."""
    global _AI_TABLES_READY
    import database
    import tenant_scope

    tenant_scope.SCOPED_TABLES.update({"ai_user_rules", "ai_signals", "ai_outcomes"})
    if _AI_TABLES_READY:
        return
    with _AI_TABLES_LOCK:
        if _AI_TABLES_READY:
            return
        kind = database._get_db_kind()
        if kind == "postgres":
            statements = [
                """
                CREATE TABLE IF NOT EXISTS ai_user_rules (
                    id TEXT PRIMARY KEY, created_at TIMESTAMP, title TEXT,
                    rule_text TEXT, parsed_json JSONB, enabled INTEGER,
                    user_id INTEGER, portfolio_id INTEGER
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS ai_signals (
                    id TEXT PRIMARY KEY, created_at TIMESTAMP, symbol TEXT, sector TEXT,
                    timeframe TEXT, horizon_days INTEGER, strategy_name TEXT,
                    market_trend TEXT, regime TEXT, ctx_key TEXT, horizons_json JSONB,
                    features_json JSONB, report_json JSONB, user_id INTEGER, portfolio_id INTEGER
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS ai_outcomes (
                    id TEXT PRIMARY KEY, signal_id TEXT, horizon_days INTEGER,
                    return_pct DOUBLE PRECISION, win INTEGER, exit_reason TEXT,
                    hit_tp INTEGER, hit_sl INTEGER, max_dd_pct DOUBLE PRECISION,
                    max_ru_pct DOUBLE PRECISION, exit_price DOUBLE PRECISION,
                    exit_at TIMESTAMP, context_json JSONB, user_id INTEGER, portfolio_id INTEGER
                )
                """,
            ]
        else:
            statements = [
                """
                CREATE TABLE IF NOT EXISTS ai_user_rules (
                    id TEXT PRIMARY KEY, created_at TEXT, title TEXT, rule_text TEXT,
                    parsed_json TEXT, enabled INTEGER, user_id INTEGER, portfolio_id INTEGER
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS ai_signals (
                    id TEXT PRIMARY KEY, created_at TEXT, symbol TEXT, sector TEXT,
                    timeframe TEXT, horizon_days INTEGER, strategy_name TEXT,
                    market_trend TEXT, regime TEXT, ctx_key TEXT, horizons_json TEXT,
                    features_json TEXT, report_json TEXT, user_id INTEGER, portfolio_id INTEGER
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS ai_outcomes (
                    id TEXT PRIMARY KEY, signal_id TEXT, horizon_days INTEGER,
                    return_pct REAL, win INTEGER, exit_reason TEXT, hit_tp INTEGER,
                    hit_sl INTEGER, max_dd_pct REAL, max_ru_pct REAL, exit_price REAL,
                    exit_at TEXT, context_json TEXT, user_id INTEGER, portfolio_id INTEGER
                )
                """,
            ]
        for statement in statements:
            if not database.execute_query(statement):
                raise RuntimeError("تعذر تهيئة جداول المستشار المعزولة")
        _AI_TABLES_READY = True

def _tenant_weight_key(key: str) -> str:
    from tenant_scope import current_tenant

    tenant = current_tenant()
    if tenant is None:
        raise RuntimeError("لا يوجد سياق محفظة لتعلم المستشار")
    return f"u{tenant.user_id}:p{tenant.portfolio_id}:{str(key)}"


def install_ai_learning_scope() -> None:
    """Prefix learned model weights so one user cannot alter another's model."""
    global _LEARNING_SCOPE_INSTALLED
    if _LEARNING_SCOPE_INSTALLED:
        return

    from ai_engine_core import logging_learning

    original_get = logging_learning._get_weight
    original_set = logging_learning._set_weight

    def get_weight_scoped(key: str, default: float = 1.0) -> float:
        try:
            return float(original_get(_tenant_weight_key(key), default))
        except Exception:
            return float(default)

    def set_weight_scoped(key: str, weight: float) -> bool:
        try:
            return bool(original_set(_tenant_weight_key(key), weight))
        except Exception:
            return False

    logging_learning._get_weight = get_weight_scoped
    logging_learning._set_weight = set_weight_scoped
    _LEARNING_SCOPE_INSTALLED = True
