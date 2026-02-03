# ai_engine_core/__init__.py

from .config import AI_ENGINE_VERSION, AI_ENGINE_NAME, AI_ENGINE_OK
from .reporting import generate_ai_report
from .portfolio import (
    calculate_portfolio_risk_score,
    run_stress_test,
    generate_rebalancing_suggestions,
)
from .user_rules import save_user_rule, load_user_rules
from .logging_learning import (  # type: ignore
    log_ai_signal,
    update_ai_outcome,
    learn_from_history,
    _get_weight,
)

# ✅ Backward-compatible aliases expected by some UIs
def generate(symbol: str, timeframe: str = "1D", **kwargs):
    """
    ✅ بعض الواجهات القديمة/الجديدة تتوقع اسم generate بدل generate_ai_report
    """
    return generate_ai_report(symbol, timeframe=timeframe)


def generate_report(symbol: str, timeframe: str = "1D", **kwargs):
    return generate_ai_report(symbol, timeframe=timeframe)


def self_test() -> dict:
    """
    ✅ تشخيص سريع بدون كسر البرنامج
    الهدف: الواجهة كانت تتوقع وجود self_test وتعرض نتيجته.
    """
    rep = {
        "ok": True,
        "engine": AI_ENGINE_NAME,
        "version": AI_ENGINE_VERSION,
        "checks": {},
        "reason": None,
    }

    # 1) تحقق من DB (اختياري)
    try:
        from .db import _safe_import_db
        execute_query, fetch_table = _safe_import_db()
        rep["checks"]["db_available"] = bool(execute_query and fetch_table)
    except Exception as e:
        rep["checks"]["db_available"] = False
        rep["checks"]["db_error"] = repr(e)

    # 2) تحقق من market_data.get_chart_history
    try:
        from market_data import get_chart_history  # noqa
        rep["checks"]["market_data_ok"] = True
    except Exception as e:
        rep["checks"]["market_data_ok"] = False
        rep["checks"]["market_data_error"] = repr(e)
        rep["ok"] = False
        rep["reason"] = "market_data missing get_chart_history"

    # 3) تحقق من financial_analysis.get_advanced_fundamental_ratios (اختياري)
    try:
        from financial_analysis import get_advanced_fundamental_ratios  # noqa
        rep["checks"]["fundamental_ok"] = True
    except Exception as e:
        rep["checks"]["fundamental_ok"] = False
        rep["checks"]["fundamental_error"] = repr(e)
        if rep["reason"] is None:
            rep["reason"] = "financial_analysis missing get_advanced_fundamental_ratios"

    # 4) تحقق من وجود generate_ai_report
    rep["checks"]["has_generate_ai_report"] = callable(globals().get("generate_ai_report"))

    return rep
