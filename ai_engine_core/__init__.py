# ai_engine_core/__init__.py
"""Lightweight package exports with one cached analysis context per report."""
from .config import AI_ENGINE_NAME, AI_ENGINE_OK, AI_ENGINE_VERSION

__all__ = [
    "AI_ENGINE_VERSION",
    "AI_ENGINE_NAME",
    "AI_ENGINE_OK",
    "DECISION_ENGINE_VERSION",
    "generate_ai_report",
    "generate",
    "generate_report",
    "self_test",
    "calculate_portfolio_risk_score",
    "run_stress_test",
    "generate_rebalancing_suggestions",
    "save_user_rule",
    "load_user_rules",
    "log_ai_signal",
    "update_ai_outcome",
    "learn_from_history",
    "_get_weight",
]


def _lazy_attr(module_name: str, attr_name: str):
    from importlib import import_module

    module = import_module(module_name, package=__name__)
    return getattr(module, attr_name)


def _report_call_context(args, kwargs) -> tuple[str, str]:
    symbol = kwargs.get("symbol")
    timeframe = kwargs.get("timeframe")
    if symbol is None and args:
        symbol = args[0]
    if timeframe is None and len(args) > 1:
        timeframe = args[1]
    return str(symbol or ""), str(timeframe or "1D")


def generate_ai_report(*args, **kwargs):
    """Build market data once, reuse it, then enforce the final v5 decision."""
    # Some workers and tests call this package directly without entering app.py.
    # Install the bounded providers/context/runtime before reporting imports bind
    # direct market-data functions.
    from sc_runtime_v9 import install_sc_runtime_v9

    install_sc_runtime_v9()
    _lazy_attr(".reporting_policy_v5", "install_reporting_policy")()
    from analysis_context_v7 import generate_with_context

    symbol, timeframe = _report_call_context(args, kwargs)
    refresh = bool(kwargs.pop("refresh", False))
    report_generator = _lazy_attr(".reporting", "generate_ai_report")

    if str(getattr(report_generator, "__module__", "")).startswith(
        "ai_engine_core"
    ):
        raw_report, _context = generate_with_context(
            report_generator,
            symbol,
            timeframe,
            refresh=refresh,
        )
    else:
        # Injected/test generators preserve their exact contract and do not
        # trigger market I/O merely because they were injected.
        raw_report = report_generator(symbol, timeframe=timeframe)

    return _lazy_attr(".decision_policy_v5", "enrich_report")(
        raw_report,
        symbol=symbol,
        timeframe=timeframe,
    )


def calculate_portfolio_risk_score(*args, **kwargs):
    return _lazy_attr(".portfolio", "calculate_portfolio_risk_score")(
        *args,
        **kwargs,
    )


def run_stress_test(*args, **kwargs):
    return _lazy_attr(".portfolio", "run_stress_test")(*args, **kwargs)


def generate_rebalancing_suggestions(*args, **kwargs):
    return _lazy_attr(
        ".portfolio",
        "generate_rebalancing_suggestions",
    )(*args, **kwargs)


def save_user_rule(*args, **kwargs):
    return _lazy_attr(".user_rules", "save_user_rule")(*args, **kwargs)


def load_user_rule(*args, **kwargs):
    """Backward-compatible singular alias."""
    return _lazy_attr(".user_rules", "load_user_rules")(*args, **kwargs)


def load_user_rules(*args, **kwargs):
    return _lazy_attr(".user_rules", "load_user_rules")(*args, **kwargs)


def log_ai_signal(*args, **kwargs):
    return _lazy_attr(".logging_learning", "log_ai_signal")(*args, **kwargs)


def update_ai_outcome(*args, **kwargs):
    return _lazy_attr(".logging_learning", "update_ai_outcome")(
        *args,
        **kwargs,
    )


def learn_from_history(*args, **kwargs):
    return _lazy_attr(".logging_learning", "learn_from_history")(
        *args,
        **kwargs,
    )


def _get_weight(*args, **kwargs):
    return _lazy_attr(".logging_learning", "_get_weight")(*args, **kwargs)


def generate(symbol: str, timeframe: str = "1D", **kwargs):
    return generate_ai_report(symbol, timeframe=timeframe, **kwargs)


def generate_report(symbol: str, timeframe: str = "1D", **kwargs):
    return generate_ai_report(symbol, timeframe=timeframe, **kwargs)


def self_test() -> dict:
    """Run safe capability checks without exposing raw exception details."""
    report = {
        "ok": True,
        "engine": AI_ENGINE_NAME,
        "version": AI_ENGINE_VERSION,
        "decision_version": DECISION_ENGINE_VERSION,
        "checks": {},
        "reason": None,
    }

    try:
        from .db import _safe_import_db

        execute_query, fetch_table = _safe_import_db()
        report["checks"]["db_available"] = bool(
            execute_query and fetch_table
        )
    except Exception:
        report["checks"]["db_available"] = False
        report["checks"]["db_error"] = (
            "database capability unavailable"
        )

    try:
        from market_data import get_chart_history  # noqa: F401

        report["checks"]["market_data_ok"] = True
    except Exception:
        report["checks"]["market_data_ok"] = False
        report["checks"]["market_data_error"] = (
            "market data capability unavailable"
        )
        report["ok"] = False
        report["reason"] = "market_data missing get_chart_history"

    try:
        from financial_analysis import (  # noqa: F401
            get_advanced_fundamental_ratios,
        )

        report["checks"]["fundamental_ok"] = True
    except Exception:
        report["checks"]["fundamental_ok"] = False
        report["checks"]["fundamental_error"] = (
            "fundamental capability unavailable"
        )
        if report["reason"] is None:
            report["reason"] = (
                "financial_analysis missing "
                "get_advanced_fundamental_ratios"
            )

    report["checks"]["has_generate_ai_report"] = callable(
        globals().get("generate_ai_report")
    )
    report["checks"]["has_decision_engine"] = callable(
        _lazy_attr(".decision_policy_v5", "enrich_report")
    )
    report["checks"]["has_breakout_engine"] = callable(
        _lazy_attr(".breakout_patterns_v91", "analyze_breakout_patterns")
    )
    report["checks"]["full_timeframe_routing"] = callable(
        _lazy_attr(".reporting_policy_v5", "timeframe_to_interval")
    )
    report["checks"]["analysis_context_v9"] = True
    return report


DECISION_ENGINE_VERSION = _lazy_attr(
    ".decision_policy_v5",
    "DECISION_ENGINE_VERSION",
)
