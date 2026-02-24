# ai_engine_core/__init__.py

"""Lightweight package exports with lazy imports.

يقلل زمن إعادة تحميل Streamlit ويمنع فشل استيراد اختبارات/وحدات بسيطة
بسبب اعتماديات ثقيلة (مثل streamlit) عند استيراد الحزمة فقط.
"""

from .config import AI_ENGINE_VERSION, AI_ENGINE_NAME, AI_ENGINE_OK

__all__ = [
    # meta
    "AI_ENGINE_VERSION",
    "AI_ENGINE_NAME",
    "AI_ENGINE_OK",

    # main
    "generate_ai_report",
    "generate",
    "generate_report",
    "self_test",

    # portfolio
    "calculate_portfolio_risk_score",
    "run_stress_test",
    "generate_rebalancing_suggestions",

    # user rules
    "save_user_rule",
    "load_user_rules",

    # learning/logging
    "log_ai_signal",
    "update_ai_outcome",
    "learn_from_history",
    "_get_weight",
]


def _lazy_attr(module_name: str, attr_name: str):
    from importlib import import_module
    mod = import_module(module_name, package=__name__)
    return getattr(mod, attr_name)


def generate_ai_report(*args, **kwargs):
    return _lazy_attr('.reporting', 'generate_ai_report')(*args, **kwargs)


def calculate_portfolio_risk_score(*args, **kwargs):
    return _lazy_attr('.portfolio', 'calculate_portfolio_risk_score')(*args, **kwargs)


def run_stress_test(*args, **kwargs):
    return _lazy_attr('.portfolio', 'run_stress_test')(*args, **kwargs)


def generate_rebalancing_suggestions(*args, **kwargs):
    return _lazy_attr('.portfolio', 'generate_rebalancing_suggestions')(*args, **kwargs)


def save_user_rule(*args, **kwargs):
    return _lazy_attr('.user_rules', 'save_user_rule')(*args, **kwargs)


def load_user_rule(*args, **kwargs):
    # backward-friendly alias if any code calls singular form by mistake
    return _lazy_attr('.user_rules', 'load_user_rules')(*args, **kwargs)


def load_user_rules(*args, **kwargs):
    return _lazy_attr('.user_rules', 'load_user_rules')(*args, **kwargs)


def log_ai_signal(*args, **kwargs):
    return _lazy_attr('.logging_learning', 'log_ai_signal')(*args, **kwargs)


def update_ai_outcome(*args, **kwargs):
    return _lazy_attr('.logging_learning', 'update_ai_outcome')(*args, **kwargs)


def learn_from_history(*args, **kwargs):
    return _lazy_attr('.logging_learning', 'learn_from_history')(*args, **kwargs)


def _get_weight(*args, **kwargs):
    return _lazy_attr('.logging_learning', '_get_weight')(*args, **kwargs)


def generate(symbol: str, timeframe: str = "1D", **kwargs):
    return generate_ai_report(symbol, timeframe=timeframe, **kwargs)


def generate_report(symbol: str, timeframe: str = "1D", **kwargs):
    return generate_ai_report(symbol, timeframe=timeframe, **kwargs)


def self_test() -> dict:
    rep = {
        "ok": True,
        "engine": AI_ENGINE_NAME,
        "version": AI_ENGINE_VERSION,
        "checks": {},
        "reason": None,
    }

    # 1) DB
    try:
        from .db import _safe_import_db
        execute_query, fetch_table = _safe_import_db()
        rep["checks"]["db_available"] = bool(execute_query and fetch_table)
    except Exception as e:
        rep["checks"]["db_available"] = False
        rep["checks"]["db_error"] = repr(e)

    # 2) market_data.get_chart_history
    try:
        from market_data import get_chart_history  # noqa
        rep["checks"]["market_data_ok"] = True
    except Exception as e:
        rep["checks"]["market_data_ok"] = False
        rep["checks"]["market_data_error"] = repr(e)
        rep["ok"] = False
        rep["reason"] = "market_data missing get_chart_history"

    # 3) financial_analysis.get_advanced_fundamental_ratios
    try:
        from financial_analysis import get_advanced_fundamental_ratios  # noqa
        rep["checks"]["fundamental_ok"] = True
    except Exception as e:
        rep["checks"]["fundamental_ok"] = False
        rep["checks"]["fundamental_error"] = repr(e)
        if rep["reason"] is None:
            rep["reason"] = "financial_analysis missing get_advanced_fundamental_ratios"

    # 4) has generate_ai_report
    rep["checks"]["has_generate_ai_report"] = callable(globals().get("generate_ai_report"))

    return rep
