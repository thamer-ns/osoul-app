# ai_engine_core/scenarios.py
from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def _price_from_df(price_df) -> float:
    try:
        if price_df is None:
            return 0.0
        if getattr(price_df, "empty", True):
            return 0.0
        for c in ["Close", "close", "Adj Close", "adj_close", "last", "Last"]:
            if c in price_df.columns:
                return _to_float(price_df[c].iloc[-1], 0.0)
        last_row = price_df.iloc[-1]
        for v in list(last_row.values)[::-1]:
            fv = _to_float(v, 0.0)
            if fv > 0:
                return fv
        return 0.0
    except Exception:
        return 0.0


def _levels_from_pack(tech_pack: Dict[str, Any]) -> Dict[str, List[float]]:
    """Extract best-effort support/resistance levels from the technical pack."""
    supports: List[float] = []
    resistances: List[float] = []

    if not isinstance(tech_pack, dict):
        return {"support": supports, "resistance": resistances}

    # common keys we might have in different implementations
    for k in ["support_levels", "supports", "support", "sr_support", "demand_zones", "zones_support"]:
        v = tech_pack.get(k)
        if isinstance(v, list):
            supports += [_to_float(x, 0.0) for x in v]
        elif isinstance(v, (int, float, str)):
            supports.append(_to_float(v, 0.0))

    for k in ["resistance_levels", "resistances", "resistance", "sr_resistance", "supply_zones", "zones_resistance"]:
        v = tech_pack.get(k)
        if isinstance(v, list):
            resistances += [_to_float(x, 0.0) for x in v]
        elif isinstance(v, (int, float, str)):
            resistances.append(_to_float(v, 0.0))

    # pivots sometimes include S1/S2/R1/R2
    piv = tech_pack.get("pivots")
    if isinstance(piv, dict):
        for kk in ["S1", "S2", "S3", "PP"]:
            if kk in piv:
                supports.append(_to_float(piv.get(kk), 0.0))
        for kk in ["R1", "R2", "R3"]:
            if kk in piv:
                resistances.append(_to_float(piv.get(kk), 0.0))

    # clean
    supports = sorted([x for x in supports if x > 0], reverse=True)
    resistances = sorted([x for x in resistances if x > 0])

    # de-dup with rounding
    def _dedup(vals: List[float]) -> List[float]:
        out = []
        seen = set()
        for x in vals:
            key = round(float(x), 3)
            if key not in seen:
                out.append(float(x))
                seen.add(key)
        return out

    return {"support": _dedup(supports)[:5], "resistance": _dedup(resistances)[:5]}


def build_scenarios(
    symbol: str,
    packs: Optional[Dict[str, Any]] = None,
    price_df=None,
) -> List[Dict[str, Any]]:
    """Build simple, explainable scenarios.

    This module exists primarily to satisfy the refactor in reporting.py:
      from .scenarios import build_scenarios

    It is intentionally best-effort and never raises.
    """
    sym = str(symbol or "").strip().upper()
    packs = packs or {}

    tech = packs.get("technical") or {}
    fund = packs.get("fundamental") or {}
    vsa = packs.get("vsa") or {}
    risk = packs.get("risk") or {}

    price = _price_from_df(price_df)
    if price <= 0:
        price = _to_float((tech or {}).get("price", 0.0), 0.0)

    levels = _levels_from_pack(tech)
    supports = levels.get("support", [])
    resistances = levels.get("resistance", [])

    # confidence heuristic from available packs
    avail = 0
    for k in [tech, fund, vsa, risk]:
        if isinstance(k, dict) and k:
            avail += 1
    base_conf = 0.35 + (avail / 4.0) * 0.5  # 0.35..0.85
    base_conf = _clamp(base_conf, 0.2, 0.9)

    scenarios: List[Dict[str, Any]] = []

    # Determine bias from scores if present
    tech_s = _to_float((tech or {}).get("score", 0.0), 0.0)
    fund_s = _to_float((fund or {}).get("score", 0.0), 0.0)
    vsa_s = _to_float((vsa or {}).get("score", 0.0), 0.0)

    bullish_votes = sum([1 for s in [tech_s, fund_s, vsa_s] if s >= 60])
    bearish_votes = sum([1 for s in [tech_s, fund_s, vsa_s] if s <= 40])
    if bullish_votes > bearish_votes:
        bias = "bullish"
    elif bearish_votes > bullish_votes:
        bias = "bearish"
    else:
        bias = "neutral"

    # helpers to pick levels around price
    def _nearest_above(vals: List[float], p: float) -> float:
        for x in sorted(vals):
            if x > p:
                return x
        return 0.0

    def _nearest_below(vals: List[float], p: float) -> float:
        for x in sorted(vals, reverse=True):
            if x < p:
                return x
        return 0.0

    r1 = _nearest_above(resistances, price) if price > 0 else (resistances[0] if resistances else 0.0)
    s1 = _nearest_below(supports, price) if price > 0 else (supports[0] if supports else 0.0)

    # --- Scenario 1: Breakout ---
    if price > 0 and r1 > 0:
        entry = r1
        stop = s1 if s1 > 0 else price * 0.94
        t1 = entry * 1.03
        t2 = entry * 1.06
        scenarios.append({
            "name": "اختراق مقاومة",
            "type": "breakout",
            "bias": "bullish",
            "entry": float(round(entry, 4)),
            "stop": float(round(stop, 4)),
            "targets": [float(round(t1, 4)), float(round(t2, 4))],
            "confidence": float(round(base_conf * (0.9 if bias == "bearish" else 1.0), 2)),
            "rationale": [
                f"الدخول بعد اختراق/إغلاق فوق المقاومة {round(r1, 4)}.",
                "الوقف أسفل أقرب دعم/منطقة طلب أو نسبة ثابتة إذا لم تتوفر مستويات.",
            ],
        })

    # --- Scenario 2: Pullback to support ---
    if price > 0 and s1 > 0:
        entry = s1
        stop = entry * 0.97
        t1 = price if price > entry else entry * 1.02
        t2 = (r1 if r1 > 0 else entry * 1.05)
        scenarios.append({
            "name": "ارتداد من دعم",
            "type": "pullback",
            "bias": "bullish" if bias != "bearish" else "neutral",
            "entry": float(round(entry, 4)),
            "stop": float(round(stop, 4)),
            "targets": [float(round(t1, 4)), float(round(t2, 4))],
            "confidence": float(round(base_conf, 2)),
            "rationale": [
                f"الدخول قرب الدعم {round(s1, 4)} مع إشارة انعكاس/تأكيد.",
                "الوقف تحت الدعم بنسبة بسيطة لإدارة المخاطر.",
            ],
        })

    # --- Scenario 3: Breakdown / rejection ---
    if price > 0:
        # Use support if available, else use 3% below price
        breakdown = s1 if s1 > 0 else price * 0.97
        stop = r1 if r1 > 0 else price * 1.03
        t1 = breakdown * 0.98
        t2 = breakdown * 0.95
        scenarios.append({
            "name": "كسر دعم / رفض من مقاومة",
            "type": "breakdown",
            "bias": "bearish",
            "entry": float(round(breakdown, 4)),
            "stop": float(round(stop, 4)),
            "targets": [float(round(t1, 4)), float(round(t2, 4))],
            "confidence": float(round(base_conf * (1.0 if bias == "bearish" else 0.85), 2)),
            "rationale": [
                "سيناريو دفاعي: في حال كسر دعم مهم أو ظهور رفض قوي من مقاومة.",
                "يُستخدم كتخفيض مخاطرة/خروج أو للبيع للمضارب المتقدم.",
            ],
        })

    # attach risk gate context if present
    try:
        rg = packs.get("risk") or {}
        if isinstance(rg, dict) and rg:
            for sc in scenarios:
                sc["risk_level"] = rg.get("risk_level", "")
                sc["risk_score"] = _to_float(rg.get("risk_score", 0.0), 0.0)
    except Exception:
        pass

    # ensure stable output
    for sc in scenarios:
        sc["symbol"] = sym

    return scenarios[:5]


# ==============================================================
# ✅ Compatibility: compute_osoli_score (required by reporting.py)
# ==============================================================


def compute_osoli_score(symbol: str, packs: Dict[str, Any]) -> Dict[str, Any]:
    """Compute an overall Osoli Score (0..100) in a stable schema.

    Some UI/reporting code imports this symbol directly. Earlier refactors
    introduced regressions where the function was missing, which breaks the
    AI report generation path.

    Returns:
      {
        "symbol": "XXXX",
        "score": int 0..100,
        "grade": "A".."F",
        "confidence": float 0..1,
        "components": {"fundamental":.., "technical":.., "vsa":.., "classical":..},
        "issues": [..]
      }
    """

    sym = str(symbol or "").strip().upper()
    packs = packs or {}
    issues: List[str] = []

    fund = packs.get("fundamental") or {}
    tech = packs.get("technical") or {}
    vsa = packs.get("vsa") or {}
    classical = packs.get("classical") or {}

    def _pack_score(p: Any) -> float:
        if isinstance(p, dict):
            if "score" in p:
                return _clamp(_to_float(p.get("score"), 0.0), 0.0, 100.0)
            # best-effort inference
            if any(k in p for k in ("Piotroski", "Graham", "Valuation")):
                s = 0.0
                s += _to_float(p.get("Piotroski"), 0.0) * 6.0
                s += _to_float(p.get("Graham"), 0.0) * 10.0
                s += _to_float(p.get("Valuation"), 0.0) * 10.0
                return _clamp(s, 0.0, 100.0)
        return 0.0

    fund_score = _pack_score(fund)
    tech_score = _pack_score(tech)
    vsa_score = _pack_score(vsa)
    cls_score = _pack_score(classical)

    present = sum(1 for p in (fund, tech, vsa, classical) if isinstance(p, dict) and len(p) > 0)
    confidence = 0.35 + 0.15 * present
    confidence = float(_clamp(confidence * 100.0, 0.0, 100.0) / 100.0)
    if present <= 1:
        issues.append("حزم التحليل غير مكتملة؛ تم حساب درجة تقريبية فقط.")

    # weights
    w_f, w_t, w_v, w_c = 0.40, 0.35, 0.15, 0.10
    score = fund_score * w_f + tech_score * w_t + vsa_score * w_v + cls_score * w_c
    score = int(round(_clamp(score, 0.0, 100.0)))

    if score >= 85:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 65:
        grade = "C"
    elif score >= 55:
        grade = "D"
    elif score >= 45:
        grade = "E"
    else:
        grade = "F"

    return {
        "symbol": sym,
        "score": score,
        "grade": grade,
        "confidence": confidence,
        "components": {
            "fundamental": float(round(fund_score, 2)),
            "technical": float(round(tech_score, 2)),
            "vsa": float(round(vsa_score, 2)),
            "classical": float(round(cls_score, 2)),
        },
        "issues": issues,
    }
