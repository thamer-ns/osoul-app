import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# الجزء 1: تحليل السهم الفردي
# ============================================================

def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 20: return 0, []
    score = 0; obs = []
    curr = df.iloc[-1]; prev = df.iloc[-2]
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    avg_spread = (df['High'] - df['Low']).rolling(20).mean().iloc[-1]
    current_spread = curr['High'] - curr['Low']
    current_vol = curr['Volume']
    
    if current_vol > avg_vol * 1.5 and current_spread < avg_spread * 0.8:
        if curr['Close'] > prev['Close']: score -= 2; obs.append("VSA: جهد شرائي عالٍ بمدى ضيق (تصريف محتمل)")
        else: score += 2; obs.append("VSA: جهد بيعي عالٍ بمدى ضيق (تجميع محتمل)")
    return score, obs

def _analyze_dow_theory_murphy(df):
    if df is None or len(df) < 200: return 0, [], "غير مؤكد"
    score = 0; obs = []
    trend_status = "عرضي"
    last_close = df['Close'].iloc[-1]
    sma_200 = df['Close'].rolling(200).mean().iloc[-1]
    
    if last_close > sma_200:
        score += 2; trend_status = "صاعد (Bull)"; obs.append("السعر فوق متوسط 200 يوم")
    else:
        score -= 2; trend_status = "هابط (Bear)"; obs.append("السعر تحت متوسط 200 يوم")
    return score, obs, trend_status

def _detect_candlestick_patterns(df):
    if df is None or len(df) < 5: return 0, []
    score = 0; patterns = []
    curr = df.iloc[-1]; prev = df.iloc[-2]
    if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']: 
        if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']: 
            score += 2; patterns.append("ابتلاع شرائي")
    return score, patterns

def _analyze_deep_financials(symbol):
    metrics = get_advanced_fundamental_ratios(symbol) 
    score = 0; obs = []
    f_score = metrics.get('Piotroski_Score', 0)
    if f_score >= 7: score += 3; obs.append(f"مركز مالي قوي (F-Score {f_score})")
    elif f_score <= 3: score -= 3; obs.append("ضعف مالي")
    return score, obs, metrics

def generate_ai_report(symbol):
    try:
        df = get_chart_history(symbol, period='2y')
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        s_dow, o_dow, trend = _analyze_dow_theory_murphy(df)
        s_can, o_can = _detect_candlestick_patterns(df)
        s_fun, o_fun, m_fun = _analyze_deep_financials(symbol)
        
        total_score = s_vsa + s_dow + s_can + s_fun
        
        recommendation = "محايد / مراقبة"; color = "#6c757d"
        strategy = "الإشارات متباينة."
        
        if total_score >= 6: recommendation = "💎 شراء قوي"; color = "#198754"; strategy = "توافق فني ومالي ممتاز."
        elif total_score >= 3: recommendation = "✅ شراء / تجميع"; color = "#28a745"; strategy = "إيجابية عامة."
        elif total_score <= -3: recommendation = "⛔ خروج / تجنب"; color = "#dc3545"; strategy = "سلبية واضحة."

        return {
            "recommendation": recommendation, "color": color, "strategy": strategy,
            "tech_reasons": o_dow + o_vsa + o_can, "fund_reasons": o_fun, "trend": trend
        }
    except Exception as e:
        return {"recommendation": "خطأ", "color": "gray", "strategy": str(e), "tech_reasons": [], "fund_reasons": []}

# ============================================================
# الجزء 2: الذكاء الاستراتيجي للمحفظة (هذا الجزء كان ناقصاً عندك)
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    try:
        if trades_df.empty: return 0
        score = 50
        if cash_percent < 10: score += 20
        if cash_percent > 50: score -= 20
        return min(max(score, 0), 100)
    except: return 50

def run_stress_test(portfolio_value, open_positions_df):
    try:
        if open_positions_df.empty: return {"scenarios": [], "insight": "محفظة كاش."}
        total_val = open_positions_df['market_value'].sum()
        scenarios = [
            {"scenario": "هبوط حاد -20%", "market_chg": -0.20, "color": "#8B0000"},
            {"scenario": "صعود +10%", "market_chg": 0.10, "color": "#059669"},
        ]
        results = []
        for s in scenarios:
            impact = total_val * s['market_chg']
            results.append({"scenario": s['scenario'], "impact_pct": s['market_chg']*100, "color": s['color']})
        return {"scenarios": results, "insight": "تحليل الحساسية للسوق."}
    except: return {"scenarios": [], "insight": ""}

def generate_rebalancing_suggestions(trades_df, cash_pct):
    suggs = []
    if cash_pct < 5: suggs.append(("priority", "السيولة منخفضة جداً (<5%)"))
    return suggs
