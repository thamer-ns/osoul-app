# ai_engine_core/risk.py

import pandas as pd
import numpy as np

from .technicals import _pivot_points


def _support_resistance_zones(df, lookback=120, max_levels=6):
    """
    يرجع (lows, highs) كمستويات Pivot Zones.
    تحسينات:
    - حماية من الأعمدة الناقصة/البيانات الفاسدة
    - تنظيف NaN وتكرار القيم
    """
    if df is None or df.empty or len(df) < max(lookback, 30):
        return [], []

    if "High" not in df.columns or "Low" not in df.columns:
        return [], []

    d = df.tail(int(lookback)).copy()
    h = pd.to_numeric(d["High"], errors="coerce")
    l = pd.to_numeric(d["Low"], errors="coerce")

    h = h.dropna()
    l = l.dropna()
    if h.empty or l.empty:
        return [], []

    try:
        ph = _pivot_points(h, 3, 3, "high") or []
        pl = _pivot_points(l, 3, 3, "low") or []
    except Exception:
        return [], []

    highs = [float(p[1]) for p in ph if isinstance(p, (list, tuple)) and len(p) >= 2 and pd.notna(p[1])]
    lows = [float(p[1]) for p in pl if isinstance(p, (list, tuple)) and len(p) >= 2 and pd.notna(p[1])]

    # إزالة التكرار مع الحفاظ على الترتيب
    def _dedup(vals):
        out, seen = [], set()
        for x in vals:
            k = round(float(x), 6)
            if k in seen:
                continue
            out.append(float(x))
            seen.add(k)
        return out

    highs = _dedup(highs)[-int(max_levels):] if highs else []
    lows = _dedup(lows)[-int(max_levels):] if lows else []
    return lows, highs


def _analyze_sr(df):
    """
    SR score بسيط لكنه ثابت:
    +1 قرب دعم
    -1 قرب مقاومة
    -2 كسر دعم مؤكّد (إغلاق يومين تحت الدعم)
    """
    if df is None or df.empty or len(df) < 120:
        return 0, [], {}

    if "Close" not in df.columns or "High" not in df.columns or "Low" not in df.columns:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"near_support": 0, "near_resistance": 0, "broke_support_confirm": 0}

    close = float(pd.to_numeric(df["Close"].iloc[-1], errors="coerce") or 0.0)
    if close <= 0:
        return 0, [], feats

    lows, highs = _support_resistance_zones(df, lookback=120, max_levels=6)

    # نسبة "القرب" من المستوى (1% افتراضي)
    near_th = 0.01

    if lows:
        sup = min(lows, key=lambda x: abs(close - x))
        if abs(close - sup) / max(close, 1e-9) < near_th:
            score += 1
            feats["near_support"] = 1
            obs.append("🧩 قرب منطقة دعم (Zone)")

        # كسر دعم مؤكد: إغلاق يومين تحت الدعم
        try:
            c1 = float(pd.to_numeric(df["Close"].iloc[-1], errors="coerce") or 0.0)
            c2 = float(pd.to_numeric(df["Close"].iloc[-2], errors="coerce") or 0.0)
            if (c1 > 0) and (c2 > 0) and (c1 < sup) and (c2 < sup):
                score -= 2
                feats["broke_support_confirm"] = 1
                obs.append("🧨 كسر دعم مؤكّد (إغلاق يومين تحت المنطقة)")
        except Exception:
            pass

    if highs:
        res = min(highs, key=lambda x: abs(close - x))
        if abs(close - res) / max(close, 1e-9) < near_th:
            score -= 1
            feats["near_resistance"] = 1
            obs.append("🧩 قرب منطقة مقاومة (Zone)")

    return score, obs, feats


def _risk_plan_from_atr_sr(df, ind, direction="buy"):
    """
    خطة مخاطرة ATR-based (بسيطة وفعّالة) مع دعم buy/sell/neutral.
    - إذا neutral: نخلي direction=neutral ونرجع stop/target لكن بدون توصية دخول قوية
    - يمنع SL/TP غير منطقية
    """
    if df is None or df.empty or "Close" not in df.columns:
        return {}

    close = float(pd.to_numeric(df["Close"].iloc[-1], errors="coerce") or 0.0)
    if close <= 0:
        return {}

    atr = ind.get("atr14")
    atrv = float(atr.iloc[-1]) if isinstance(atr, pd.Series) and len(atr) and pd.notna(atr.iloc[-1]) else None

    direction = (direction or "buy").lower().strip()
    if direction not in ("buy", "sell", "neutral"):
        direction = "buy"

    plan = {
        "entry": round(float(close), 4),
        "stop": None,
        "target1": None,
        "rr": None,
        "direction": direction,
    }

    if atrv is None or atrv <= 0:
        return plan

    # معاملات افتراضية
    sl_mult = 2.0
    tp_mult = 3.0

    if direction == "sell":
        stop = close + sl_mult * atrv
        target1 = close - tp_mult * atrv
    else:
        # buy أو neutral (نحط نفس الحساب لكن direction يبقى neutral)
        stop = close - sl_mult * atrv
        target1 = close + tp_mult * atrv

    # حماية: stop/target لازم تكون أرقام معقولة
    if stop <= 0 or target1 <= 0:
        return plan

    plan["stop"] = round(float(stop), 4)
    plan["target1"] = round(float(target1), 4)

    risk = abs(close - stop)
    reward = abs(target1 - close)
    rr = (reward / risk) if risk > 0 else 0.0
    plan["rr"] = round(float(rr), 2)

    return plan


def _risk_gates(report: dict) -> dict:
    """
    بوابات المخاطر (لا تغيّر الواجهة):
    - RR حد أدنى
    - كسر دعم مؤكّد يمنع الشراء
    - OCF سالب يمنع الاستثمار (كما عندك)
    """
    gates = {"pass": True, "reasons": []}
    rp = report.get("risk_plan") or {}
    rr = rp.get("rr", None)

    # Gate 1: RR
    try:
        if rr is not None:
            rr = float(rr)
            if rr > 0 and rr < 1.2:
                gates["pass"] = False
                gates["reasons"].append("R:R أقل من 1.2 — مخاطرة غير مناسبة")
    except Exception:
        pass

    feats = report.get("features") or {}

    # Gate 2: broke support confirm => يمنع الشراء
    try:
        broke = int(feats.get("broke_support_confirm") or 0)
        rec = str(report.get("recommendation") or "")
        is_buy_like = ("شراء" in rec) or ("Buy" in rec) or ("Strong Buy" in rec)
        if broke == 1 and is_buy_like:
            gates["pass"] = False
            gates["reasons"].append("كسر دعم مؤكّد — يمنع الشراء")
    except Exception:
        pass

    # Gate 3: OCF negative
    try:
        if int(feats.get("fund_neg_ocf") or 0) == 1:
            gates["pass"] = False
            gates["reasons"].append("التدفق النقدي التشغيلي سالب — مخاطرة عالية للاستثمار")
    except Exception:
        pass

    return gates


def _build_scenarios(df: pd.DataFrame, report: dict) -> list:
    if df is None or df.empty or "Close" not in df.columns:
        return []

    close = float(pd.to_numeric(df["Close"].iloc[-1], errors="coerce") or 0.0)
    if close <= 0:
        return []

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
                "note": "يفضّل مع حجم داعم/زخم + عدم وجود مقاومات قريبة أعلى.",
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
                "note": "أفضل إذا ظهرت إشارات قوة/تجميع (VSA/OBV/RSI).",
            }
        )

    if int(feats.get("broke_support_confirm") or 0) == 1 and near_sup is not None:
        scenarios.append(
            {
                "name": "سيناريو فشل",
                "trigger": f"إغلاق يومين تحت الدعم ~ {near_sup:.2f}",
                "action": "خروج/تقليل مركز أو وقف خسارة",
                "note": "متوافق مع broke_support_confirm + يحمي من التعلّق بالسهم.",
            }
        )

    return scenarios[:5]


def _calc_confidence(tech_score, fund_score, df):
    """
    Confidence = 0..100 (ثابت)
    تحسين بسيط: جودة البيانات + قوة الإشارة + توافق الفني/المالي
    """
    quality = 5
    n = int(len(df)) if df is not None else 0
    if n >= 220:
        quality = 30
    elif n >= 120:
        quality = 25
    elif n >= 60:
        quality = 15

    try:
        strength = min(abs(float(tech_score) + float(fund_score)) * 8, 45)
    except Exception:
        strength = 0

    try:
        alignment = 25 if ((tech_score >= 0 and fund_score >= 0) or (tech_score <= 0 and fund_score <= 0)) else 10
    except Exception:
        alignment = 10

    conf = int(min(quality + strength + alignment, 100))
    if conf >= 75:
        label = "عالية"
    elif conf >= 50:
        label = "متوسطة"
    else:
        label = "منخفضة"
    return conf, label


def _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score):
    """
    تحسين بسيط:
    - Dedup
    - تصنيف positives/negatives أقرب للواقع
    """
    positives, negatives, notes = [], [], []
    pos_keys = [
        "اختراق", "BMS", "OTE", "نجمة", "ابتلاع", "قوة", "Order Block",
        "Ichimoku صاعد", "Bias شرائي", "Stopping", "دعم", "✅", "💎", "🔀 تقاطع",
        "قاعدة مستخدم", "Golden Cross", "ADX", "OBV", "Inside Bar", "No Supply"
    ]

    def _dedup(items):
        out, seen = [], set()
        for x in (items or []):
            s = str(x).strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            out.append(s)
            seen.add(k)
        return out

    tech_reasons = _dedup(tech_reasons)
    fund_reasons = _dedup(fund_reasons)

    for x in tech_reasons:
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    for x in fund_reasons:
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    notes.append(f"Tech={tech_score} | Fund={fund_score} | Total={total_score}")

    if tech_score > 3 and fund_score < 0:
        notes.append("تعارض: الفني قوي لكن المالي ضعيف — الأفضل مضاربة بإدارة مخاطر.")
    if fund_score > 3 and tech_score < 0:
        notes.append("تعارض: المالي قوي والسعر ضعيف — مناسب لاستثمار قيمة بصبر.")

    exp = {
        "positives": positives[:10],
        "negatives": negatives[:10],
        "notes": notes[:10],
    }
    exp["top_evidence"] = exp["positives"][:3]
    exp["top_risks"] = exp["negatives"][:3]
    return exp


def _infer_strategy_hint(module_scores: dict):
    if not module_scores:
        return "Mixed"
    k = max(module_scores.keys(), key=lambda x: abs(module_scores.get(x, 0) or 0))
    return str(k)
