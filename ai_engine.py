# ai_engine.py
# ------------------------------------------------------------
# Facade module:
# The UI (views/*) imports from `ai_engine`. Keep this file tiny
# and stable and delegate real work to `ai_engine_core`.
# ------------------------------------------------------------

from ai_engine_core import (
    AI_ENGINE_VERSION,
    AI_ENGINE_NAME,
    AI_ENGINE_OK,
    generate_ai_report,
    calculate_portfolio_risk_score,
    run_stress_test,
    generate_rebalancing_suggestions,
    save_user_rule,
    load_user_rules,
)

__all__ = [
    "AI_ENGINE_VERSION",
    "AI_ENGINE_NAME",
    "AI_ENGINE_OK",
    "generate_ai_report",
    "generate",
    "generate_report",
    "calculate_portfolio_risk_score",
    "run_stress_test",
    "generate_rebalancing_suggestions",
    "save_user_rule",
    "load_user_rules",
]


def generate(symbol: str, timeframe: str = "1D", **kwargs):
    """Backward-compatible alias."""
    return generate_ai_report(symbol, timeframe=timeframe)


def generate_report(symbol: str, timeframe: str = "1D", **kwargs):
    """Backward-compatible alias."""
    return generate_ai_report(symbol, timeframe=timeframe)
