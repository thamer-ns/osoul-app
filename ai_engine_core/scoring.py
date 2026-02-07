# ai_engine_core/scoring.py
from __future__ import annotations

from typing import Any, Dict, Tuple, List


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if not s:
            return float(default)
        s = s.replace(",", "")
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        s = s.replace("SAR", "").replace("ر.س", "").strip()
        if s.lower() in ("nan", "none", "null", "na"):
            return float(default)
        return float(s)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _score_from_pack(pack: Dict[str, Any]) -> float:
    """
    Standardize extracting 'score' from a pack.
    Pack contract (best-effort):
      - pack["score"] may exist and be 0..100
      - else compute a heuristic based on evidence length + ok flags
    """
    if not isinstance(pack, dict) or not pack:
        return 0.0

    # direct score
    s = pack.get("score", None)
    if s is not None:
        return _clamp(_to_float(s, 0.0), 0.0, 100.0)

    # heuristic fallback
    ok = pack.get("ok", True)
    evidence = pack.get("evidence", []) or []
    evn = len(evidence) if isinstance(evidence, list) else 0

    base = 50.0
    if ok is False:
        base -= 15.0
    base += min(evn * 2.0, 20.0)  # up to +20

    return _clamp(base, 0.0, 100.0)


def _weight_map() -> Dict[str, float]:
    """
    Default weights. Adjust later if needed.
    """
    return {
        "technical": 0.40,
        "fundamental": 0.35,
        "vsa": 0.15,
        "risk": 0.10,  # risk here is a modifier pack
    }


def _risk_adjustment(risk_pack: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Convert risk issues into a penalty factor.
    Returns: (penalty_points, issues_list)
    """
    issues = []
    penalty = 0.0

    if isinstance(risk_pack, dict):
        # common keys
        risk_score = risk_pack.get("risk_score", None)
        if risk_score is not None:
            # risk_score expected 0..100 (higher risk)
            rs = _clamp(_to_float(risk_score, 0.0), 0.0, 100.0)
            # map to penalty 0..25
            penalty += (rs / 100.0) * 25.0

        iss = risk_pack.get("issues", None)
        if isinstance(iss, list):
            issues.extend([str(x) for x in iss if str(x).strip()][:10])

        # sometimes flags
        if risk_pack.get("ok") is False:
            penalty += 5.0

    penalty = _clamp(penalty, 0.0, 35.0)
    return float(penalty), issues


def compute_osoli_score(symbol: str, packs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main API expected by ai_engine_core.reporting.py

    Input:
      symbol: str
      packs: dict with keys like:
        - packs["technical"] -> dict (score/evidence/ok/notes)
        - packs["fundamental"] -> dict
        - packs["vsa"] -> dict
        - packs["risk"] -> dict (risk_score/issues)

    Output dict (stable):
      {
        "ok": bool,
        "symbol": str,
        "score": float (0..100),
        "rating": str,
        "signals": {...},
        "components": {...},
        "penalties": {...},
        "notes": str
      }
    """
    sym = str(symbol or "").strip().upper()
    packs = packs or {}

    weights = _weight_map()

    tech = packs.get("technical") or {}
    fund = packs.get("fundamental") or {}
    vsa = packs.get("vsa") or {}
    risk = packs.get("risk") or {}

    tech_s = _score_from_pack(tech)
    fund_s = _score_from_pack(fund)
    vsa_s = _score_from_pack(vsa)

    # weighted base score
    base = (
        tech_s * weights["technical"]
        + fund_s * weights["fundamental"]
        + vsa_s * weights["vsa"]
    )

    # risk penalty
    penalty, risk_issues = _risk_adjustment(risk)
    score = _clamp(base - penalty, 0.0, 100.0)

    # rating buckets
    if score >= 80:
        rating = "A"
    elif score >= 70:
        rating = "B"
    elif score >= 55:
        rating = "C"
    elif score >= 40:
        rating = "D"
    else:
        rating = "E"

    # simple signals
    signals = {
        "technical_bias": "bullish" if tech_s >= 65 else ("bearish" if tech_s <= 35 else "neutral"),
        "fundamental_bias": "bullish" if fund_s >= 65 else ("bearish" if fund_s <= 35 else "neutral"),
        "vsa_bias": "bullish" if vsa_s >= 60 else ("bearish" if vsa_s <= 40 else "neutral"),
        "risk_level": "high" if penalty >= 18 else ("medium" if penalty >= 9 else "low"),
    }

    components = {
        "technical": float(round(tech_s, 2)),
        "fundamental": float(round(fund_s, 2)),
        "vsa": float(round(vsa_s, 2)),
        "base_weighted": float(round(base, 2)),
    }

    penalties = {
        "risk_penalty": float(round(penalty, 2)),
        "risk_issues": risk_issues,
    }

    notes = ""
    if isinstance(tech, dict) and tech.get("notes"):
        notes += f"TECH: {str(tech.get('notes')).strip()}  "
    if isinstance(fund, dict) and fund.get("notes"):
        notes += f"FUND: {str(fund.get('notes')).strip()}  "
    if isinstance(vsa, dict) and vsa.get("notes"):
        notes += f"VSA: {str(vsa.get('notes')).strip()}  "

    out = {
        "ok": True,
        "symbol": sym,
        "score": float(round(score, 2)),
        "rating": rating,
        "signals": signals,
        "components": components,
        "penalties": penalties,
        "notes": notes.strip(),
    }
    return out