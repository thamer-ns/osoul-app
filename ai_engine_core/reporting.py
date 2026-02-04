# ai_engine_core/reporting.py
from typing import Dict, Any
import pandas as pd

from .scoring import osoli_score, recommendation_from_score, build_evidence, merge_features
from .risk import _risk_gates, _build_scenarios, _calc_confidence


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
        "risk": 0.0,  # ممكن نضيفه لاحقاً
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
            for rr in (g.get("reasons") or []):
                # نضع سبب كfeature نصي لا
                pass
            # flag للتركيز/السيولة
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

    # gates (من ملف risk.py عندك)
    gates = _risk_gates(report)
    report["gates"] = gates

    # scenarios (من ملف risk.py عندك)
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
