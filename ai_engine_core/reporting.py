from osoli_logging import log_exception
# ai_engine_core/reporting.py

import traceback
import pandas as pd

from .config import AI_ENGINE_NAME, AI_ENGINE_VERSION
from .core import _normalize_symbol, _to_float, _round2
from .packs import build_technical_pack, build_vsa_pack, build_fundamental_pack
from .scoring import compute_osoli_score
from .risk import build_risk_gates
from .scenarios import build_scenarios


def _stance_from_score(score: float) -> str:
    """Convert numeric score into stance label."""
    try:
        s = float(score)
    except Exception:
        s = 0.0
    if s >= 70:
        return "bullish"
    if s <= 30:
        return "bearish"
    return "neutral"


def _confidence_from_scores(scores: dict) -> float:
    """Estimate confidence based on pack availability and score consistency."""
    try:
        available = 0
        total = 0
        for k in ["technical", "fundamental", "vsa", "risk"]:
            total += 1
            if scores.get(k, None) is not None:
                available += 1
        base = available / max(total, 1)

        # penalize extreme disagreement
        vals = []
        for k in ["technical", "fundamental", "vsa"]:
            v = scores.get(k, None)
            if v is not None:
                vals.append(float(v))
        if len(vals) >= 2:
            spread = max(vals) - min(vals)
        else:
            spread = 0.0

        # spread 0..100 -> penalty 0..0.35
        penalty = min(max(spread / 100.0, 0.0), 1.0) * 0.35
        conf = max(min(base - penalty + 0.35, 0.99), 0.15)
        return float(conf)
    except Exception:
        return 0.35


def _build_factor_opinions(packs: dict, scores: dict) -> list:
    """Create multi-factor advisor opinions with evidence + confidence."""
    opinions = []

    # Technical factor
    tech = packs.get("technical") or {}
    tech_score = scores.get("technical")
    opinions.append({
        "factor": "technical",
        "stance": _stance_from_score(tech_score if tech_score is not None else 50),
        "score": _to_float(tech_score, 0.0),
        "confidence": 0.55 if tech else 0.25,
        "evidence": tech.get("evidence", []),
        "notes": tech.get("notes", ""),
    })

    # Fundamental factor
    fund = packs.get("fundamental") or {}
    fund_score = scores.get("fundamental")
    opinions.append({
        "factor": "fundamental",
        "stance": _stance_from_score(fund_score if fund_score is not None else 50),
        "score": _to_float(fund_score, 0.0),
        "confidence": 0.60 if fund else 0.25,
        "evidence": fund.get("evidence", []),
        "notes": fund.get("notes", ""),
    })

    # VSA factor
    vsa = packs.get("vsa") or {}
    vsa_score = scores.get("vsa")
    opinions.append({
        "factor": "vsa",
        "stance": _stance_from_score(vsa_score if vsa_score is not None else 50),
        "score": _to_float(vsa_score, 0.0),
        "confidence": 0.50 if vsa else 0.20,
        "evidence": vsa.get("evidence", []),
        "notes": vsa.get("notes", ""),
    })

    # Risk factor
    risk = packs.get("risk") or {}
    risk_score = scores.get("risk")
    opinions.append({
        "factor": "risk",
        "stance": "neutral" if risk else "neutral",
        "score": _to_float(risk_score, 0.0),
        "confidence": 0.70 if risk else 0.25,
        "evidence": risk.get("issues", []),
        "notes": risk.get("notes", ""),
    })

    return opinions


def generate_ai_report(symbol: str, price_df: pd.DataFrame = None, financial_df: pd.DataFrame = None) -> dict:
    """
    Build the full AI report with:
    - Packs (technical/vsa/fundamental)
    - Osoli score + signals
    - Risk gates
    - Scenarios
    - Multi-factor advisor opinions
    """
    try:
        sym = _normalize_symbol(symbol)
        report = {
            "engine": {"name": AI_ENGINE_NAME, "version": AI_ENGINE_VERSION},
            "symbol": sym,
            "packs": {},
            "scores": {},
            "osoli": {},
            "risk_gates": {},
            "scenarios": [],
            "advisor_factors": [],
            "advisor_summary": {},
            "errors": [],
        }

        # -------------------------
        # Build packs
        # -------------------------
        packs = {}
        scores = {}

        try:
            packs["technical"] = build_technical_pack(sym, price_df=price_df)
        except Exception as e:
            packs["technical"] = {"ok": False, "error": str(e), "evidence": [], "notes": ""}
            report["errors"].append(f"technical_pack: {str(e)}")

        try:
            packs["vsa"] = build_vsa_pack(sym, price_df=price_df)
        except Exception as e:
            packs["vsa"] = {"ok": False, "error": str(e), "evidence": [], "notes": ""}
            report["errors"].append(f"vsa_pack: {str(e)}")

        try:
            packs["fundamental"] = build_fundamental_pack(sym, financial_df=financial_df)
        except Exception as e:
            packs["fundamental"] = {"ok": False, "error": str(e), "evidence": [], "notes": ""}
            report["errors"].append(f"fundamental_pack: {str(e)}")

        # -------------------------
        # Compute Osoli score
        # -------------------------
        try:
            osoli = compute_osoli_score(sym, packs)
            report["osoli"] = osoli or {}
        except Exception as e:
            report["osoli"] = {"ok": False, "error": str(e)}
            report["errors"].append(f"osoli_score: {str(e)}")

        # -------------------------
        # Scores per pack (0..100) best-effort
        # -------------------------
        try:
            tech_score = (packs.get("technical") or {}).get("score", None)
            fund_score = (packs.get("fundamental") or {}).get("score", None)
            vsa_score = (packs.get("vsa") or {}).get("score", None)

            scores["technical"] = _to_float(tech_score, None)
            scores["fundamental"] = _to_float(fund_score, None)
            scores["vsa"] = _to_float(vsa_score, None)
        except Exception:
            pass

        # -------------------------
        # Risk gates + scenarios
        # -------------------------
        try:
            risk_gates = build_risk_gates(sym, packs, price_df=price_df)
            report["risk_gates"] = risk_gates or {}
            # make a risk score
            scores["risk"] = _to_float((risk_gates or {}).get("risk_score", None), None)
            packs["risk"] = risk_gates or {}
        except Exception as e:
            report["risk_gates"] = {"ok": False, "error": str(e)}
            report["errors"].append(f"risk_gates: {str(e)}")

        try:
            scenarios = build_scenarios(sym, packs, price_df=price_df)
            report["scenarios"] = scenarios or []
        except Exception as e:
            report["scenarios"] = []
            report["errors"].append(f"scenarios: {str(e)}")

        # -------------------------
        # Attach packs & scores
        # -------------------------
        report["packs"] = packs
        report["scores"] = scores

        # -------------------------
        # Multi-factor advisor opinions
        # -------------------------
        try:
            opinions = _build_factor_opinions(packs, scores)
            report["advisor_factors"] = opinions

            overall_conf = _confidence_from_scores(scores)
            bullish = [x for x in opinions if x.get("stance") == "bullish"]
            bearish = [x for x in opinions if x.get("stance") == "bearish"]
            neutral = [x for x in opinions if x.get("stance") == "neutral"]

            report["advisor_summary"] = {
                "overall_confidence": float(overall_conf),
                "bullish_factors": [x.get("factor") for x in bullish],
                "bearish_factors": [x.get("factor") for x in bearish],
                "neutral_factors": [x.get("factor") for x in neutral],
                "overall_stance": "bullish" if len(bullish) > len(bearish) else ("bearish" if len(bearish) > len(bullish) else "neutral"),
            }
        except Exception as e:
            report["advisor_factors"] = []
            report["advisor_summary"] = {"overall_confidence": 0.35, "overall_stance": "neutral", "error": str(e)}
            report["errors"].append(f"advisor_split: {str(e)}")

        return report

    except Exception as e:
        log_exception(e, "AI report failed", level="ERROR")
        return {
            "engine": {"name": AI_ENGINE_NAME, "version": AI_ENGINE_VERSION},
            "symbol": symbol,
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }