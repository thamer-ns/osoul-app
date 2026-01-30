import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🕯️ 1) Advanced Candlestick Patterns
# ============================================================
def _detect_advanced_patterns(df):
    if df is None or len(df) < 5:
        return 0, []

    score = 0
    patterns = []

    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    body1 = abs(c1["Close"] - c1["Open"])
    body2 = abs(c2["Close"] - c2["Open"])
    body3 = abs(c3["Close"] - c3["Open"])

    is_c1_red = c1["Close"] < c1["Open"]
    is_c1_green = c1["Close"] > c1["Open"]
    is_c2_red = c2["Close"] < c2["Open"]
    is_c2_green = c2["Close"] > c2["Open"]
    is_c3_green = c3["Close"] > c3["Open"]
    is_c3_red = c3["Close"] < c3["Open"]

    # Morning Star
    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1["Open"] - (body1 / 2)
        if c3["Close"] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح (Morning Star) - إشارة انعكاس إيجابية قوية")

    # Evening Star
    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1["Open"] + (body1 / 2)
        if c3["Close"] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء (Evening Star) - إشارة خروج سلبية")

    # Bullish Harami
    if is_c2_red and is_c3_green and c3["Open"] > c2["Close"] and c3["Close"] < c2["Open"]:
        score += 2
        patterns.append("🤰 الحرامي الشرائي (Bullish Harami) - ضعف الزخم الهابط")

    # Bullish Engulfing
    if is_c2_red and is_c3_green and c3["Open"] < c2["Close"] and c3["Close"] > c2["Open"]:
        score += 2
        patterns.append("🔥 الابتلاع الشرائي (Bullish Engulfing) - سيطرة المشترين")

    return score, patterns


# ============================================================
# 📈 2) Market Structure
# ============================================================
def _analyze_market_structure(df):
    if df is None or len(df) < 30:
        return 0, []

    score = 0
    obs = []

    curr_price = float(df["Close"].iloc[-1])
    last_peak = float(df["High"].iloc[-25:-2].max())
    last_valley = float(df["Low"].iloc[-25:-2].min())

    if curr_price > last_peak:
        score += 3
        obs.append(f"🚀 اختراق قمة سابقة ({last_peak:.2f}) - إشارة دخول صريحة")
    elif curr_price < last_valley:
        score -= 3
        obs.append(f"⚠️ كسر قاع سابق ({last_valley:.2f}) - إشارة خروج (وقف خسارة)")
    else:
        range_size = last_peak - last_valley
        if range_size > 0:
            pos = (curr_price - last_valley) / range_size
            if pos > 0.8:
                score += 1
                obs.append("السعر يختبر القمة السابقة (مراقبة)")
            elif pos < 0.2:
                score -= 1
                obs.append("السعر يختبر القاع السابق (حذر)")
            else:
                score -= 1
                obs.append("مسار عرضي (تذبذب)")

    return score, obs


# ============================================================
# 💰 3) Fundamental Golden Rules
# ============================================================
def _analyze_financial_golden_rules(symbol):
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except Exception:
        return 0, [], {}

    score = 0
    obs = []

    try:
        piotroski = metrics.get("Piotroski_Score", 0)
        if piotroski >= 7:
            score += 3
            obs.append("💎 أساسيات قوية جداً (جودة أرباح وملاءة عالية)")
        elif piotroski <= 3:
            score -= 3
            obs.append("❌ تحذير: الشركة هشة مالياً")

        fv = metrics.get("Fair_Value_Graham", 0)
        rating = metrics.get("Rating", "")
        if fv and fv > 0 and ("قوي" in str(rating) or "جيد" in str(rating)):
            score += 2
            obs.append("✅ السهم يتداول عند تقييم مالي عادل")

        ops_str = str(metrics.get("Opinions", ""))
        if ("سالب" in ops_str) and (("تشغيلي" in ops_str) or ("نقد" in ops_str)):
            score -= 4
            obs.append("⚠️ خطر: التدفق النقدي التشغيلي سالب (الشركة تنزف كاش)")
    except Exception:
        pass

    return score, obs, metrics


# ============================================================
# 📊 4) VSA (Art of Trading)
# ============================================================
def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 20:
        return 0, []

    score = 0
    obs = []

    curr = df.iloc[-1]
    avg_vol = float(df["Volume"].iloc[-20:].mean())

    if float(curr["Volume"]) > avg_vol * 1.5:
        range_size = float(curr["High"] - curr["Low"])
        avg_range = float((df["High"] - df["Low"]).iloc[-20:].mean())
        if avg_range > 0 and range_size < avg_range * 0.8:
            obs.append("VSA: فوليوم عالي بمدى ضيق (احتمال تلاعب)")

    return score, obs


# ============================================================
# ✅ Confidence + Explainability (Helpers)
# ============================================================
def _calc_confidence(tech_score, fund_score, df):
    quality = 0
    if df is not None and len(df) >= 120:
        quality += 25
    elif df is not None and len(df) >= 60:
        quality += 15
    else:
        quality += 5

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

    pos_keys = ["اختراق", "نجمة", "ابتلاع", "سيطرة", "إشارة دخول", "قوية", "ملاءة", "عادل", "جيد", "✅", "💎"]

    for x in (tech_reasons or []):
        if any(k in x for k in pos_keys):
            positives.append(x)
        else:
            negatives.append(x)

    for x in (fund_reasons or []):
        if any(k in x for k in pos_keys):
            positives.append(x)
        else:
            negatives.append(x)

    notes.append(f"Tech Score = {tech_score} | Fund Score = {fund_score} | Total = {total_score}")

    if tech_score > 3 and fund_score < 0:
        notes.append("يوجد تعارض: الفني قوي لكن المالي ضعيف — الأفضل مضاربة بإدارة مخاطر.")
    if fund_score > 3 and tech_score < 0:
        notes.append("يوجد تعارض: المالي قوي لكن السعر ضعيف — مناسب لاستثمار قيمة بصبر.")

    return {"positives": positives[:10], "negatives": negatives[:10], "notes": notes[:10]}


# ============================================================
# 🧠 Master Brain
# ============================================================
def generate_ai_report(symbol):
    try:
        df = get_chart_history(symbol, period="6mo")

        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)

        tech_score = s_candle + s_struct + s_vsa
        fund_score = s_fund
        total_score = tech_score + fund_score

        rec = "⚖️ محايد / مراقبة"
        clr = "#6c757d"
        strat = "السعر في منطقة حيرة. انتظر إشارة أوضح."

        if total_score >= 7:
            rec = "💎 فرصة ماسية (Strong Buy)"
            clr = "#198754"
            strat = "توافق مذهل: اختراق قمة + نموذج إيجابي + مالية قوية."
        elif total_score >= 4:
            rec = "✅ شراء / تجميع"
            clr = "#28a745"
            strat = "الإشارات الإيجابية تغلب. الهيكلية صاعدة."
        elif total_score <= -4:
            rec = "⛔ خروج / وقف خسارة"
            clr = "#dc3545"
            strat = "كسر قاع سابق أو نموذج سلبي. الحذر واجب."
        elif tech_score > 3 and fund_score < 0:
            rec = "⚡ مضاربة بحذر"
            clr = "#ffc107"
            strat = "فني ممتاز (اختراق) ولكن الشركة ضعيفة مالياً."
        elif fund_score > 4 and tech_score < 0:
            rec = "📉 استثمار قيمة"
            clr = "#0d6efd"
            strat = "السعر يهبط لكن الشركة قوية جداً."

        tech_reasons = (o_struct or []) + (o_candle or []) + (o_vsa or [])
        fund_reasons = o_fund or []

        if not tech_reasons:
            tech_reasons = ["حركة السعر طبيعية"]
        if not fund_reasons:
            fund_reasons = ["المؤشرات المالية طبيعية"]

        confidence, confidence_label = _calc_confidence(tech_score, fund_score, df)
        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)

        return {
            "recommendation": rec,
            "color": clr,
            "strategy": strat,
            "tech_score": tech_score,
            "fund_score": fund_score,
            "tech_reasons": tech_reasons,
            "fund_reasons": fund_reasons,
            "trend": "صاعد" if s_struct > 0 else "هابط",
            "confidence": confidence,
            "confidence_label": confidence_label,
            "explainability": explainability,
        }

    except Exception:
        return {
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص بيانات",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
        }


# ============================================================
# 🛡️ Portfolio Intelligence (كما عندك)
# ============================================================
def calculate_portfolio_risk_score(trades_df, cash_percent):
    try:
        if trades_df.empty:
            return 0

        open_trades = trades_df[trades_df["status"] == "Open"]
        if open_trades.empty:
            return 0

        total_market_val = float(open_trades["market_value"].sum())
        if total_market_val == 0:
            return 0

        max_asset_weight = (float(open_trades["market_value"].max()) / total_market_val) * 100
        concentration_score = 30 if max_asset_weight > 50 else (15 if max_asset_weight > 25 else 0)

        liquidity_score = 25 if cash_percent < 5 else (10 if cash_percent < 15 else 0)

        strategy_score = 0
        try:
            spec_ratio = len(open_trades[open_trades["strategy"].astype(str).str.contains("مضاربة", na=False)]) / len(open_trades)
            strategy_score = spec_ratio * 30
        except Exception:
            pass

        return min(round(concentration_score + liquidity_score + strategy_score, 1), 100)
    except Exception:
        return 50


def run_stress_test(portfolio_value, open_positions_df):
    try:
        if open_positions_df.empty:
            return {"scenarios": [], "insight": "المحفظة كاش."}

        weighted_beta = 0
        total_val = float(open_positions_df["market_value"].sum())
        if total_val == 0:
            return {"scenarios": [], "insight": "غير متاح"}

        for _, row in open_positions_df.iterrows():
            w = float(row["market_value"]) / total_val
            if row.get("asset_type") == "Sukuk":
                b = 0.1
            elif "مضاربة" in str(row.get("strategy", "")):
                b = 1.2
            else:
                b = 0.9
            weighted_beta += (w * b)

        scenarios = [
            {"name": "انهيار (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
            {"name": "طفرة (+20%)", "market_chg": 0.20, "color": "#047857"},
        ]

        results = []
        for s in scenarios:
            impact_pct = s["market_chg"] * weighted_beta
            results.append({"scenario": s["name"], "impact_pct": impact_pct * 100, "color": s["color"]})

        insight = "المحفظة عالية التذبذب" if weighted_beta > 1.1 else "المحفظة متوازنة"
        return {"scenarios": results, "insight": insight}
    except Exception:
        return {"scenarios": [], "insight": "غير متاح"}


def generate_rebalancing_suggestions(trades_df, cash_pct):
    suggestions = []
    try:
        if cash_pct < 5:
            suggestions.append(("priority", "🚨 السيولة منخفضة جداً (< 5%)"))

        if not trades_df.empty:
            open_trades = trades_df[trades_df["status"] == "Open"]
            for _, row in open_trades.iterrows():
                if float(row.get("gain_pct", 0) or 0) < -10:
                    suggestions.append(("danger", f"🛑 خسارة تجاوزت -10% في {row.get('symbol','-')}"))
    except Exception:
        pass

    return suggestions
