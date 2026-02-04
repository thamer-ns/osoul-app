# ai_engine_core/__init__.py

from __future__ import annotations

# =========================================================
# Meta (safe import)
# =========================================================
try:
    from .config import AI_ENGINE_VERSION, AI_ENGINE_NAME, AI_ENGINE_OK
except Exception:
    AI_ENGINE_VERSION = "unknown"
    AI_ENGINE_NAME = "Osoli AI Engine"
    AI_ENGINE_OK = False

# =========================================================
# Main (safe import)
# =========================================================
_report_import_error = None
try:
    from .reporting import generate_ai_report  # noqa
except Exception as e:
    _report_import_error = repr(e)

    def generate_ai_report(symbol: str, timeframe: str = "1D", **kwargs):
        return {
            "status": "error",
            "__error__": "generate_ai_report import failed",
            "__trace__": _report_import_error,
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص ملفات/استيراد داخل ai_engine_core",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
            "features": {},
            "gates": {"pass": False, "reasons": ["AI Engine Error"]},
            "scenarios": [],
            "engine_meta": {
                "engine": AI_ENGINE_NAME,
                "version": AI_ENGINE_VERSION,
                "timeframe": str(timeframe),
            },
        }

# =========================================================
# Portfolio (safe import)
# =========================================================
_portfolio_import_error = None
try:
    from .portfolio import (  # noqa
        calculate_portfolio_risk_score,
        run_stress_test,
        generate_rebalancing_suggestions,
    )
except Exception as e:
    _portfolio_import_error = repr(e)

    def calculate_portfolio_risk_score(df, c):
        return 50

    def run_stress_test(v, df):
        return {"scenarios": [], "insight": "", "__warn__": "portfolio module missing", "__trace__": _portfolio_import_error}

    def generate_rebalancing_suggestions(df, c):
        return []

# =========================================================
# User rules (safe import)
# =========================================================
_user_rules_import_error = None
try:
    from .user_rules import save_user_rule, load_user_rules  # noqa
except Exception as e:
    _user_rules_import_error = repr(e)

    def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
        return {"ok": False, "reason": "user_rules module missing", "trace": _user_rules_import_error}

    def load_user_rules(enabled_only: bool = True, max_rows: int = 50):
        return []

# =========================================================
# Learning / logging (safe import)
# =========================================================
_learning_import_error = None
try:
    from .logging_learning import (  # noqa
        log_ai_signal,
        update_ai_outcome,
        learn_from_history,
        _get_weight,
    )
except Exception as e:
    _learning_import_error = repr(e)

    def log_ai_signal(*args, **kwargs):
        return None

    def update_ai_outcome(*args, **kwargs):
        return {"ok": False, "reason": "logging_learning missing", "trace": _learning_import_error}

    def learn_from_history(*args, **kwargs):
        return {"ok": False, "reason": "logging_learning missing", "trace": _learning_import_error}

    def _get_weight(key: str, default: float = 1.0):
        return float(default)

# =========================================================
# Public exports (keep your API)
# =========================================================
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


def generate(symbol: str, timeframe: str = "1D", **kwargs):
    # kwargs reserved for future extension
    return generate_ai_report(symbol, timeframe=timeframe, **kwargs)


def generate_report(symbol: str, timeframe: str = "1D", **kwargs):
    # alias
    return generate_ai_report(symbol, timeframe=timeframe, **kwargs)


def self_test() -> dict:
    rep = {
        "ok": True,
        "engine": AI_ENGINE_NAME,
        "version": AI_ENGINE_VERSION,
        "checks": {},
        "reason": None,
    }

    # 0) reporting import check
    rep["checks"]["reporting_import_ok"] = callable(globals().get("generate_ai_report"))
    if _report_import_error:
        rep["checks"]["reporting_import_error"] = _report_import_error
        rep["ok"] = False
        rep["reason"] = "reporting import failed"

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
        if rep["reason"] is None:
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

    # 5) optional modules sanity
    rep["checks"]["portfolio_module_ok"] = (_portfolio_import_error is None)
    if _portfolio_import_error:
        rep["checks"]["portfolio_import_error"] = _portfolio_import_error

    rep["checks"]["user_rules_module_ok"] = (_user_rules_import_error is None)
    if _user_rules_import_error:
        rep["checks"]["user_rules_import_error"] = _user_rules_import_error

    rep["checks"]["logging_learning_ok"] = (_learning_import_error is None)
    if _learning_import_error:
        rep["checks"]["logging_learning_error"] = _learning_import_error

    return rep
