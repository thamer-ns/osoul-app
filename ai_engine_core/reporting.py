# ai_engine_core/reporting.py

import traceback
import json
import pandas as pd

from .config import AI_ENGINE_NAME, AI_ENGINE_VERSION
from .core import _normalize_symbol, _map_period_from_timeframe
from .indicators import _ensure_ohlcv_columns, _compute_indicators
from .technicals import (
    _detect_advanced_patterns,
    _analyze_market_structure,
    _analyze_sr,
    _detect_liquidity_sweep,
    _detect_order_block,
    _analyze_ichimoku,
    _analyze_financial_golden_rules,
    _support_resistance_zones,  # إذا احتجته
)
from .learning import log_ai_signal, _get_weight
from .rules import load_user_rules, _eval_user_rule
from .risk import _risk_plan_from_atr_sr, _risk_gates, _build_scenarios
from .explain import _calc_confidence, _build_explainability, _infer_strategy_hint

def generate_ai_report(symbol, timeframe="1D"):
    # ✅ هنا انقل دالتك generate_ai_report بالكامل من ملفك الأصلي،
    # فقط:
    # 1) احذف تعريفات الدوال الداخلية (لأنها صارت في ملفات منفصلة)
    # 2) خلي الاستيرادات أعلاه هي المصدر
    symbol = _normalize_symbol(symbol)

    try:
        from market_data import get_chart_history

        period = _map_period_from_timeframe(timeframe)
        try:
            df = get_chart_history(symbol, period=period)
        except TypeError:
            df = get_chart_history(symbol, period)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise ValueError("no data")

        df = _ensure_ohlcv_columns(df)
        if df is None or df.empty or len(df) < 60:
            raise ValueError("insufficient candles")

        ind = _compute_indicators(df)

        # ... أكمل بقية منطقك كما هو من الملف الأصلي ...

        # (في نهاية التقرير)
        # report["risk_gates"] = _risk_gates(report)
        # report["scenarios"] = _build_scenarios(df, report)
        # signal_id = log_ai_signal(...)
        # return report

        return {"recommendation": "غير متاح", "engine_meta": {"engine": AI_ENGINE_NAME, "version": AI_ENGINE_VERSION}}

    except Exception as e:
        tr = traceback.format_exc()
        return {
            "__error__": str(e),
            "__trace__": tr,
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص بيانات أو خطأ داخلي",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
            "features": {},
            "calibration": {},
            "strategy_name": None,
            "sector": None,
            "risk_plan": {},
            "risk_gates": {"pass": False, "reasons": ["AI Engine Error"]},
            "scenarios": [],
            "engine_meta": {
                "engine": AI_ENGINE_NAME,
                "version": AI_ENGINE_VERSION,
                "timeframe": str(timeframe),
                "period_used": None,
                "rows": 0,
                "last_bar": None,
            },
        }
