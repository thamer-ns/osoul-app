"""Register AI tables that contain user-specific rules or reports."""
from __future__ import annotations


def register_ai_tenant_tables() -> None:
    import database
    import tenant_scope

    tenant_scope.SCOPED_TABLES.update(
        {"ai_user_rules", "ai_signals", "ai_outcomes"}
    )

    kind = database._get_db_kind()
    if kind == "postgres":
        statements = [
            """
            CREATE TABLE IF NOT EXISTS ai_user_rules (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP,
                title TEXT,
                rule_text TEXT,
                parsed_json JSONB,
                enabled INTEGER,
                user_id INTEGER,
                portfolio_id INTEGER
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_signals (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP,
                symbol TEXT,
                sector TEXT,
                timeframe TEXT,
                horizon_days INTEGER,
                strategy_name TEXT,
                market_trend TEXT,
                regime TEXT,
                ctx_key TEXT,
                horizons_json JSONB,
                features_json JSONB,
                report_json JSONB,
                user_id INTEGER,
                portfolio_id INTEGER
            )
            """,
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
                context_json JSONB,
                user_id INTEGER,
                portfolio_id INTEGER
            )
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS ai_user_rules (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                title TEXT,
                rule_text TEXT,
                parsed_json TEXT,
                enabled INTEGER,
                user_id INTEGER,
                portfolio_id INTEGER
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_signals (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                symbol TEXT,
                sector TEXT,
                timeframe TEXT,
                horizon_days INTEGER,
                strategy_name TEXT,
                market_trend TEXT,
                regime TEXT,
                ctx_key TEXT,
                horizons_json TEXT,
                features_json TEXT,
                report_json TEXT,
                user_id INTEGER,
                portfolio_id INTEGER
            )
            """,
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
                context_json TEXT,
                user_id INTEGER,
                portfolio_id INTEGER
            )
            """,
        ]

    for statement in statements:
        if not database.execute_query(statement):
            raise RuntimeError("تعذر تهيئة جداول المستشار المعزولة")
