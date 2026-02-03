# ai_engine_core/risk.py

import pandas as pd

def _risk_plan_from_atr_sr(df, ind, direction="buy"):
    if df is None or df.empty:
        return {}

    close = float(df["Close"].iloc[-1])
    atr = ind.get("atr14")
    atrv = float(atr.iloc[-1]) if isinstance(atr, pd.Series) and not pd.isna(atr.iloc[-1]) else None

    plan = {"entry": close, "stop": None, "target1": None, "rr": None, "direction": direction}
    if atrv is None or atrv <= 0:
        return plan

    direction = (direction or "buy").lower().strip()
    if direction == "sell":
        stop = close + 2.0 * atrv
        target1 = close - 3.0 * atrv
    else:
        stop = close - 2.0 * atrv
        target1 = close + 3.0 * atrv

    plan["stop"] = round(float(stop), 4)
    plan["target1"] = round(float(target1), 4)

    risk = abs(close - stop)
    reward = abs(target1 - close)
    plan["rr"] = round((reward / risk) if risk > 0 else 0, 2)
    return plan

def _risk_gates(report: dict) -> dict:
    gates = {"pass": True, "reasons": []}
    rp = report.get("risk_plan") or {}
    rr = rp.get("rr", None)

    try:
        if rr is not None and float(rr) > 0 and float(rr) < 1.2:
            gates["pass"] = False
            gates["reasons"].append("R:R أقل من 1.2 — مخاطرة غير مناسبة")
    except Exception:
        pass

    feats = report.get("features") or {}
    if int(feats.get("broke_support_confirm") or 0) == 1:
        gates["pass"] = False
        gates["reasons"].append("كسر دعم مؤكّد — يمنع الشراء")

    if int(feats.get("fund_neg_ocf") or 0) == 1:
        gates["pass"] = False
        gates["reasons"].append("التدفق النقدي التشغيلي سالب — مخاطرة عالية للاستثمار")

    return gates

def _build_scenarios(df, report: dict) -> list:
    # ✅ انسخ دالتك كما هي (الموجودة عندك ممتازة)
    # ضع هنا نفس محتوى _build_scenarios من ملفك الأصلي.
    return []
