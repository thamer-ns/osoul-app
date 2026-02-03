# ai_engine/risk.py
import pandas as pd

from .technicals import _pivot_points

def _support_resistance_zones(df, lookback=120, max_levels=6):
    if df is None or len(df) < lookback:
        return [], []
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    ph = _pivot_points(h.tail(lookback), 3, 3, "high")
    pl = _pivot_points(l.tail(lookback), 3, 3, "low")
    highs = [p[1] for p in ph][-max_levels:]
    lows = [p[1] for p in pl][-max_levels:]
    return lows, highs

def _analyze_sr(df):
    if df is None or len(df) < 120:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"near_support": 0, "near_resistance": 0, "broke_support_confirm": 0}

    close = float(df["Close"].iloc[-1])
    lows, highs = _support_resistance_zones(df)

    if lows:
        sup = min(lows, key=lambda x: abs(close - x))
        if abs(close - sup) / max(close, 1e-9) < 0.01:
            score += 1
            feats["near_support"] = 1
            obs.append("🧩 قرب منطقة دعم (Zone)")

        try:
            c1 = float(df["Close"].iloc[-1])
            c2 = float(df["Close"].iloc[-2])
            if (c1 < sup) and (c2 < sup):
                score -= 2
                feats["broke_support_confirm"] = 1
                obs.append("🧨 كسر دعم مؤكّد (إغلاق يومين تحت المنطقة)")
        except Exception:
            pass

    if highs:
        res = min(highs, key=lambda x: abs(close - x))
        if abs(close - res) / max(close, 1e-9) < 0.01:
            score -= 1
            feats["near_resistance"] = 1
            obs.append("🧩 قرب منطقة مقاومة (Zone)")

    return score, obs, feats

def _risk_plan_from_atr_sr(df, ind, direction="buy"):
    """
    ✅ تطوير بدون كسر:
    - كان عندك دائمًا Buy
    - الآن يدعم buy/sell لكن افتراضيًا buy (يعني متوافق 100%)
    """
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

    # ✅ إضافة: Gate مالي قوي (الميزة موجودة عندك أصلاً)
    if int(feats.get("fund_neg_ocf") or 0) == 1:
        gates["pass"] = False
        gates["reasons"].append("التدفق النقدي التشغيلي سالب — مخاطرة عالية للاستثمار")

    return gates

def _build_scenarios(df: pd.DataFrame, report: dict) -> list:
    if df is None or df.empty:
        return []

    close = float(df["Close"].iloc[-1])
    feats = report.get("features") or {}
    rp = report.get("risk_plan") or {}

    lows, highs = _support_resistance_zones(df, lookback=120, max_levels=6)
    near_sup = min(lows, key=lambda x: abs(close - x)) if lows else None
    near_res = min(highs, key=lambda x: abs(close - x)) if highs else None

    scenarios = []

    if near_res is not None:
        scenarios.append(
            {
                "name": "سيناريو اختراق",
                "trigger": f"إغلاق يومي فوق المقاومة ~ {near_res:.2f}",
                "entry": rp.get("entry"),
                "stop": rp.get("stop"),
                "target1": rp.get("target1"),
                "note": "يفضّل مع حجم داعم/زخم",
            }
        )

    if near_sup is not None:
        scenarios.append(
            {
                "name": "سيناريو ارتداد",
                "trigger": f"ثبات فوق الدعم ~ {near_sup:.2f} + شمعة انعكاس",
                "entry": rp.get("entry"),
                "stop": rp.get("stop"),
                "target1": rp.get("target1"),
                "note": "أفضل إذا ظهرت إشارات قوة",
            }
        )

    if int(feats.get("broke_support_confirm") or 0) == 1 and near_sup is not None:
        scenarios.append(
            {
                "name": "سيناريو فشل",
                "trigger": f"إغلاق يومين تحت الدعم ~ {near_sup:.2f}",
                "action": "خروج/تقليل مركز أو وقف خسارة",
                "note": "متوافق مع broke_support_confirm",
            }
        )

    return scenarios[:5]

def _calc_confidence(tech_score, fund_score, df):
    quality = 5
    if df is not None and len(df) >= 220:
        quality = 30
    elif df is not None and len(df) >= 120:
        quality = 25
    elif df is not None and len(df) >= 60:
        quality = 15

    strength = min(abs(tech_score + fund_score) * 8, 45)
    alignment = 25 if ((tech_score >= 0 and fund_score >= 0) or (tech_score <= 0 and fund_score <= 0)) else 10

    conf = int(min(quality + strength + alignment, 100))
    if conf >= 75:
        label = "عالية"
    elif conf >= 50:
        label = "متوسطة"
    else:
        label = "منخفضة"
    return conf, label

def _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score):
    positives, negatives, notes = [], [], []
    pos_keys = [
        "اختراق", "BMS", "OTE", "نجمة", "ابتلاع", "قوة", "Order Block",
        "Ichimoku صاعد", "Bias شرائي", "Stopping", "دعم", "✅", "💎", "🔀 تقاطع",
        "قاعدة مستخدم", "Golden Cross", "ADX", "OBV", "Inside Bar", "No Supply"
    ]

    for x in (tech_reasons or []):
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    for x in (fund_reasons or []):
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    notes.append(f"Tech={tech_score} | Fund={fund_score} | Total={total_score}")

    if tech_score > 3 and fund_score < 0:
        notes.append("تعارض: الفني قوي لكن المالي ضعيف — الأفضل مضاربة بإدارة مخاطر.")
    if fund_score > 3 and tech_score < 0:
        notes.append("تعارض: المالي قوي والسعر ضعيف — مناسب لاستثمار قيمة بصبر.")

    exp = {"positives": positives[:10], "negatives": negatives[:10], "notes": notes[:10]}
    exp["top_evidence"] = exp["positives"][:3]
    exp["top_risks"] = exp["negatives"][:3]
    return exp

def _infer_strategy_hint(module_scores: dict):
    if not module_scores:
        return "Mixed"
    k = max(module_scores.keys(), key=lambda x: abs(module_scores.get(x, 0) or 0))
    return str(k)
