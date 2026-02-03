# ai_engine_core/__init__.py

from .config import AI_ENGINE_NAME, AI_ENGINE_VERSION, AI_ENGINE_OK
from .db import _safe_import_db
from .reporting import generate_ai_report
from .rules import save_user_rule, load_user_rules
from .learning import learn_from_history, update_ai_outcome
from .portfolio import calculate_portfolio_risk_score, run_stress_test, generate_rebalancing_suggestions

# Backward-compatible aliases
generate = generate_ai_report
generate_report = generate_ai_report

def self_test() -> dict:
    rep = {
        "ok": True,
        "engine": AI_ENGINE_NAME,
        "version": AI_ENGINE_VERSION,
        "checks": {},
        "reason": None,
    }

    try:
        execute_query, fetch_table = _safe_import_db()
        rep["checks"]["db_available"] = bool(execute_query and fetch_table)
    except Exception as e:
        rep["checks"]["db_available"] = False
        rep["checks"]["db_error"] = repr(e)

    try:
        from market_data import get_chart_history  # noqa
        rep["checks"]["market_data_ok"] = True
    except Exception as e:
        rep["checks"]["market_data_ok"] = False
        rep["checks"]["market_data_error"] = repr(e)
        rep["ok"] = False
        rep["reason"] = "market_data missing get_chart_history"

    rep["checks"]["has_generate_ai_report"] = callable(generate_ai_report)
    return rep
