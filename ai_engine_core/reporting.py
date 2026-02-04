# ai_engine_core/reporting.py

from typing import Dict, Any, Optional, Tuple
import traceback
import pandas as pd

from .scoring import osoli_score, recommendation_from_score, build_evidence, merge_features
from .risk import _risk_gates, _build_scenarios, _calc_confidence


# =========================================================
# ✅ New-style builder (كما هو عندك) — لا نلمسه
# =========================================================
def build_report(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    tech_pack: Dict[str, Any],
    vsa_pack: Dict[str, Any],
    fund_pack: Dict[str, Any] = None,
    risk_plan: Dict[str, Any] = None,
    portfolio_pack: Dict[str, Any] = None,
):
    fund_pack = fund_pack or {"score": 0.0, "reasons": [], "features": {}}
    portfolio_pack = portfolio_pack or {"gates": {"pass": True, "reasons": [], "warnings": []}, "notes": []}
    risk_plan = risk_plan or {}

    module_scores = {
        "tech": float(tech_pack.get("score", 0.0) or 0.0),
        "vsa": float(vsa_pack.get("score", 0.0) or 0.0),
        "fund": float(fund_pack.get("score", 0.0) or 0.0),
        "risk": 0.0,
        "structure": 0.0,
    }

    total = osoli_score(module_scores)
    direction_hint = str(tech_pack.get("direction_hint") or "neutral")
    rec = recommendation_from_score(total, direction_hint=direction_hint)

    features = merge_features(
        tech_pack.get("features") or {},
        vsa_pack.get("features") or {},
        fund_pack.get("features") or {},
    )

    # ادمج بوابات المحفظة كfeatures
    try:
        g = (portfolio_pack.get("gates") or {})
        if isinstance(g, dict):
            if g.get("pass") is False:
                features["portfolio_gate_fail"] = 1
    except Exception:
        pass

    report = {
        "symbol": str(symbol),
        "timeframe": str(timeframe),
        "scores": {
            "module": module_scores,
            "total": round(float(total), 2),
        },
        "recommendation": rec,
        "risk_plan": risk_plan,
        "features": features,
        "modules": {
            "technical": tech_pack,
            "vsa": vsa_pack,
            "fundamental": fund_pack,
            "portfolio": portfolio_pack,
        },
    }

    # gates
    gates = _risk_gates(report)
    report["gates"] = gates

    # scenarios
    try:
        report["scenarios"] = _build_scenarios(df, report)
    except Exception:
        report["scenarios"] = []

    # explainability + confidence
    exp = build_evidence(
        tech_pack,
        vsa_pack,
        fund_pack,
        extra_notes=(portfolio_pack.get("notes") or []) + (portfolio_pack.get("gates", {}).get("warnings") or []),
    )
    report["explainability"] = exp

    try:
        conf, conf_label = _calc_confidence(
            tech_score=float(module_scores["tech"]),
            fund_score=float(module_scores["fund"]),
            df=df,
        )
        report["confidence"] = {"value": int(conf), "label": str(conf_label)}
    except Exception:
        report["confidence"] = {"value": 50, "label": "متوسطة"}

    # إذا gates fail: خفف التوصية
    if gates.get("pass") is False:
        report["recommendation"] = f"⚠️ {report['recommendation']} (مرفوض بالبوابات)"
        report["explainability"]["notes"] = (report["explainability"].get("notes") or []) + (gates.get("reasons") or [])

    return report


# =========================================================
# ✅ Backward-compatible API: generate_ai_report(symbol, timeframe)
# =========================================================
def generate_ai_report(symbol: str, timeframe: str = "1D") -> Dict[str, Any]:
    """
    This function exists ONLY to keep old imports working:
      - ai_engine_core.__init__ expects it
      - ai_engine.py / views/shared.py expects it

    It tries to:
      1) Build packs using available pack-builders (new modular engine)
      2) If pack-builders are missing, it falls back with a clear error report
    """

    try:
        # Normalize / fetch market data
        try:
            from .core import _normalize_symbol  # موجود عندك حسب traceback
        except Exception:
            _normalize_symbol = lambda x: str(x).strip().upper()

        symbol_n = _normalize_symbol(symbol)

        # Data fetch (supports your market_data module)
        from market_data import get_chart_history  # مشروعك
        from .ohlcv import _ensure_ohlcv_columns  # موجود عندك بالهيكلة القديمة

        # timeframe mapping (لو عندك)
        try:
            from .core import _map_period_from_timeframe
            period = _map_period_from_timeframe(timeframe)
        except Exception:
            period = "2y"

        # interval mapping بسيط (مثل اللي كان عندك)
        tf = str(timeframe or "").strip().upper()
        if tf in ("1H", "60M", "H"):
            interval = "60m"
        elif tf in ("30M",):
            interval = "30m"
        elif tf in ("15M",):
            interval = "15m"
        elif tf in ("5M",):
            interval = "5m"
        elif tf in ("1W", "W"):
            interval = "1wk"
        elif tf in ("1M", "MO", "MONTH"):
            interval = "1mo"
        else:
            interval = "1d"

        # Fetch history with flexible signature
        try:
            df = get_chart_history(symbol_n, period=period, interval=interval)
        except TypeError:
            df = get_chart_history(symbol_n, period)

        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            raise ValueError("no market data")

        df = _ensure_ohlcv_columns(df)
        if df is None or df.empty:
            raise ValueError("no ohlcv columns")

        # =====================================================
        # Build packs (NEW engine) if available
        # =====================================================
        tech_pack = None
        vsa_pack = None
        fund_pack = None
        risk_plan = None
        portfolio_pack = None

        pack_errors = []

        # 1) Technical pack
        try:
            from .packs import build_technical_pack  # إذا موجود عندك
            tech_pack = build_technical_pack(symbol_n, timeframe, df)
        except Exception as e:
            pack_errors.append(f"build_technical_pack: {repr(e)}")

        # 2) VSA pack
        try:
            from .packs import build_vsa_pack
            vsa_pack = build_vsa_pack(symbol_n, timeframe, df)
        except Exception as e:
            pack_errors.append(f"build_vsa_pack: {repr(e)}")

        # 3) Fundamental pack
        try:
            from .packs import build_fundamental_pack
            fund_pack = build_fundamental_pack(symbol_n, timeframe, df)
        except Exception as e:
            pack_errors.append(f"build_fundamental_pack: {repr(e)}")
            fund_pack = {"score": 0.0, "reasons": [], "features": {}}

        # 4) Risk plan (اختياري)
        try:
            from .packs import build_risk_plan_pack
            risk_plan = build_risk_plan_pack(symbol_n, timeframe, df)
        except Exception:
            risk_plan = {}

        # 5) Portfolio gates (اختياري)
        try:
            from .packs import build_portfolio_pack
            portfolio_pack = build_portfolio_pack(symbol_n, timeframe, df)
        except Exception:
            portfolio_pack = {"gates": {"pass": True, "reasons": [], "warnings": []}, "notes": []}

        # لو ما قدرنا نبني packs الأساسية
        if tech_pack is None or vsa_pack is None:
            raise RuntimeError(
                "Missing pack builders. "
                "Expected ai_engine_core/packs.py with build_technical_pack + build_vsa_pack. "
                f"Details: {pack_errors}"
            )

        report = build_report(
            symbol=symbol_n,
            timeframe=timeframe,
            df=df,
            tech_pack=tech_pack,
            vsa_pack=vsa_pack,
            fund_pack=fund_pack,
            risk_plan=risk_plan,
            portfolio_pack=portfolio_pack,
        )

        # شكل report “friendly” للتبويبة (اختياري)
        # عشان shared.py عندك يعرضها بسهولة
        try:
            report.setdefault("status", "ok")
            report.setdefault("engine_meta", {"timeframe": str(timeframe), "interval": str(interval), "rows": int(len(df))})
        except Exception:
            pass

        return report

    except Exception as e:
        tr = traceback.format_exc()
        return {
            "status": "error",
            "__error__": str(e),
            "__trace__": tr,
            "recommendation": "غير متاح",
            "scores": {"module": {}, "total": 0},
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
            "features": {},
            "gates": {"pass": False, "reasons": ["AI Engine Error"]},
            "scenarios": [],
            "engine_meta": {"timeframe": str(timeframe)},
        }
