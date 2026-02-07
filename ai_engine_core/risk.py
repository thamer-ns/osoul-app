# ai_engine_core/risk.py
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


def _safe_div(a: Any, b: Any, default: float = 0.0) -> float:
    try:
        aa = _to_float(a, 0.0)
        bb = _to_float(b, 0.0)
        if bb == 0:
            return float(default)
        return float(aa / bb)
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


def _pick(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return default


def _infer_volatility_hint(tech_pack: Dict[str, Any]) -> float:
    """
    Best-effort estimate of volatility/risk level from technical pack.
    We keep it conservative and do NOT depend on heavy indicators.
    Returns: 0..100 (higher = higher risk)
    """
    if not isinstance(tech_pack, dict) or not tech_pack:
        return 40.0

    # Try common keys
    atrp = _pick(tech_pack, ["atr_percent", "atrp", "ATR_percent"], None)
    adx = _pick(tech_pack, ["adx", "ADX"], None)
    rsi = _pick(tech_pack, ["rsi", "RSI"], None)

    risk = 40.0

    # ATR% contributes more to risk
    if atrp is not None:
        v = _to_float(atrp, 0.0)
        # map: 0..15% -> 0..60 points
        risk += _clamp((v / 15.0) * 60.0, 0.0, 60.0)

    # ADX: strong trends may reduce "chop" risk slightly (small effect)
    if adx is not None:
        a = _to_float(adx, 0.0)
        if a >= 25:
            risk -= 5.0

    # RSI extremes can increase reversal risk
    if rsi is not None:
        r = _to_float(rsi, 50.0)
        if r >= 75 or r <= 25:
            risk += 7.0

    return _clamp(risk, 0.0, 100.0)


def build_risk_gates(
    symbol: str,
    packs: Optional[Dict[str, Any]] = None,
    price_snapshot: Optional[Dict[str, Any]] = None,
    capital: Optional[float] = None,
) -> Dict[str, Any]:
    """
    API expected by ai_engine_core.reporting.py

    Goal:
      - Provide stable "risk gate" output even if some packs are missing.
      - Avoid raising exceptions (NEVER break import/runtime).
      - Keep logic minimal and safe.

    Output:
      {
        "ok": bool,
        "symbol": str,
        "pass": bool,
        "risk_score": float (0..100)  # higher = higher risk
        "risk_level": "low|medium|high",
        "position_sizing": { ... },
        "stops": { ... },
        "issues": [ ... ],
        "notes": str
      }
    """
    sym = str(symbol or "").strip().upper()
    packs = packs or {}

    tech = packs.get("technical") or {}
    fund = packs.get("fundamental") or {}
    vsa = packs.get("vsa") or {}

    # --- price ---
    price = 0.0
    if isinstance(price_snapshot, dict):
        price = _to_float(price_snapshot.get("price", 0.0), 0.0)
    # fallback: maybe in tech pack
    if price <= 0:
        price = _to_float(_pick(tech, ["price", "last_price", "close"], 0.0), 0.0)

    issues: List[str] = []

    # --- volatility hint ---
    vol_risk = _infer_volatility_hint(tech)  # 0..100

    # --- fundamental fragility hint (very light) ---
    # If missing financials -> slightly higher uncertainty risk
    fin_ok = True
    if isinstance(fund, dict):
        fin_ok = fund.get("ok", True) is not False
    if not fund:
        fin_ok = False

    # --- volume anomaly hint from VSA (very light) ---
    vsa_ok = True
    if isinstance(vsa, dict):
        vsa_ok = vsa.get("ok", True) is not False
    if not vsa:
        vsa_ok = False

    risk_score = vol_risk
    if not fin_ok:
        risk_score += 8.0
        issues.append("نقص/ضعف بيانات التحليل المالي يزيد عدم اليقين.")
    if not vsa_ok:
        risk_score += 4.0
        issues.append("نقص بيانات VSA يقلل جودة إشارات السيولة/التجميع.")

    risk_score = _clamp(risk_score, 0.0, 100.0)

    if risk_score >= 70:
        risk_level = "high"
    elif risk_score >= 45:
        risk_level = "medium"
    else:
        risk_level = "low"

    # --- basic stops suggestion (best-effort) ---
    # If ATR% is available, build a stop distance; otherwise use conservative 6%
    atrp = _to_float(_pick(tech, ["atr_percent", "atrp", "ATR_percent"], 0.0), 0.0)
    if atrp > 0:
        stop_pct = _clamp(max(atrp * 1.5, 3.5), 2.0, 15.0)  # 1.5x ATR%, bounded
    else:
        stop_pct = 6.0

    stop_price = price * (1.0 - stop_pct / 100.0) if price > 0 else 0.0

    # --- position sizing (very light) ---
    # Default risk per trade: 1% of capital. If no capital -> just return guidelines.
    pos = {
        "capital": float(_to_float(capital, 0.0)) if capital is not None else 0.0,
        "risk_per_trade_pct": 1.0 if risk_level != "high" else 0.5,
        "suggested_risk_amount": 0.0,
        "suggested_qty": 0.0,
        "note": "",
    }
    if pos["capital"] > 0 and price > 0 and stop_price > 0:
        risk_amt = pos["capital"] * (pos["risk_per_trade_pct"] / 100.0)
        per_share_risk = max(price - stop_price, 0.0)
        qty = _safe_div(risk_amt, per_share_risk, 0.0) if per_share_risk > 0 else 0.0
        pos["suggested_risk_amount"] = float(round(risk_amt, 2))
        pos["suggested_qty"] = float(round(qty, 2))
        pos["note"] = "حجم الصفقة محسوب حسب مخاطرة/صفقة ونقطة وقف."
    else:
        pos["note"] = "حدد رأس المال والسعر/الوقف لحساب حجم الصفقة بدقة."

    # --- gate decision ---
    # High risk + no price => fail gate
    passed = True
    if price <= 0:
        passed = False
        issues.append("تعذر الحصول على السعر الحالي، لا يمكن بناء مخاطرة صحيحة.")
    if risk_level == "high":
        # لا نمنع دائمًا، لكن نضع Gate إذا المخاطر عالية جدًا
        if risk_score >= 85:
            passed = False
            issues.append("مخاطر مرتفعة جدًا حسب تقدير التقلب/عدم اليقين.")

    notes = ""
    if risk_level == "high":
        notes = "بوابة المخاطرة صارمة: خفّض الحجم أو انتظر تأكيد/تقلب أقل."
    elif risk_level == "medium":
        notes = "مخاطرة متوسطة: التزم بوقف وخطة واضحة."
    else:
        notes = "مخاطرة منخفضة نسبيًا: التزم بالإدارة ولا ترفع المخاطرة."

    return {
        "ok": True,
        "symbol": sym,
        "pass": bool(passed),
        "risk_score": float(round(risk_score, 2)),
        "risk_level": risk_level,
        "position_sizing": pos,
        "stops": {
            "stop_pct": float(round(stop_pct, 2)),
            "stop_price": float(round(stop_price, 4)) if stop_price > 0 else 0.0,
        },
        "issues": issues,
        "notes": notes,
    }