# ai_engine_core/explain.py

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
