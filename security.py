import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🏛️ الجزء الأول: المحرك المعرفي (Technical & Fundamental Core)
# (تم الحفاظ عليه كما هو لضمان عدم كسر التقارير الفردية)
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
        if curr['Close'] > prev['Close']: score -= 2; obs.append("VSA: جهد شرائي عالي بمدى ضيق (إشارة تصريف محتملة)")
        else: score += 2; obs.append("VSA: جهد بيعي عالي بمدى ضيق (إشارة تجميع/امتصاص)")

    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    body_size = abs(curr['Close'] - curr['Open'])
    if lower_wick > body_size * 2 and current_vol < avg_vol:
        score += 2; obs.append("VSA: نجاح اختبار العرض (No Supply) - إشارة إيجابية")

    upper_wick = curr['High'] - max(curr['Close'], curr['Open'])
    if current_vol > avg_vol * 3 and upper_wick > body_size:
        score -= 3; obs.append("VSA: ذروة شراء (Buying Climax) - الحذر من الانعكاس")

    return score, obs

def _analyze_dow_theory_murphy(df):
    if df is None or len(df) < 200: return 0, [], "غير مؤكد"
    score = 0; obs = []
    trend_status = "عرضي"
    last_close = df['Close'].iloc[-1]
    sma_50 = df['Close'].rolling(50).mean().iloc[-1]
    sma_200 = df['Close'].rolling(200).mean().iloc[-1]
    
    if last_close > sma_200:
        if sma_50 > sma_200:
            score += 3; trend_status = "صاعد قوي (Bull Market)"; obs.append("السعر والمتوسطات في ترتيب صاعد مثالي")
        else:
            score += 1; trend_status = "صاعد ضعيف"; obs.append("السعر فوق متوسط 200 يوم لكن الزخم يضعف")
    else:
        score -= 2; trend_status = "هابط (Bear Market)"; obs.append("السعر تحت متوسط 200 يوم (سلبية رئيسية)")

    return score, obs, trend_status

def _detect_candlestick_patterns(df):
    if df is None or len(df) < 5: return 0, []
    score = 0; patterns = []
    curr = df.iloc[-1]; prev = df.iloc[-2]
    body = abs(curr['Close'] - curr['Open'])
    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    upper_wick = curr['High'] - max(curr['Close'], curr['Open'])
    
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        score += 1; patterns.append("شمعة المطرقة (Hammer)")
    if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']: 
        if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']: 
            score += 2; patterns.append("الابتلاع الشرائي (Bullish Engulfing)")
            
    return score, patterns

def _analyze_deep_financials(symbol):
    metrics = get_advanced_fundamental_ratios(symbol) 
    price = metrics.get('Current_Price', 0) 
    score = 0; obs = []
    f_score = metrics.get('Piotroski_Score', 0)
    
    if f_score >= 8: score += 3; obs.append(f"مركز مالي ممتاز (F-Score {f_score}/9)")
    elif f_score <= 3: score -= 3; obs.append("تحذير: ضعف مالي وتشغيلي")
        
    return score, obs, metrics

def generate_ai_report(symbol):
    """
    التقرير الفردي للسهم (موجود مسبقاً)
    """
    try:
        df = get_chart_history(symbol, period='2y')
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        s_dow, o_dow, trend = _analyze_dow_theory_murphy(df)
        s_can, o_can = _detect_candlestick_patterns(df)
        s_fun, o_fun, m_fun = _analyze_deep_financials(symbol)
        
        tech_score = s_vsa + s_dow + s_can
        fund_score = s_fun
        total_score = tech_score + fund_score
        
        recommendation = "محايد / مراقبة"; color = "#6c757d" 
        strategy = "تضارب الإشارات. يفضل الانتظار."
        
        if total_score >= 7: recommendation = "💎 استثمار ذهبي"; color = "#198754"; strategy = "توافق مالي وفني ممتاز."
        elif total_score >= 4: recommendation = "✅ شراء / تجميع"; color = "#28a745"; strategy = "اتجاه إيجابي."
        elif total_score <= -4: recommendation = "⛔ خروج / تجنب"; color = "#dc3545"; strategy = "إشارات سلبية متعددة."
        elif tech_score >= 3 and fund_score < 0: recommendation = "⚡ مضاربة بحذر"; color = "#ffc107"; strategy = "جيد فنياً، خطر مالياً."
        elif fund_score >= 4 and tech_score < 0: recommendation = "📉 استثمار قيمة"; color = "#0d6efd"; strategy = "شركة قوية بسعر هابط."

        tech_reasons = o_dow + o_vsa + o_can
        if not tech_reasons: tech_reasons.append("لا توجد أنماط فنية بارزة")
        fund_reasons = o_fun
        if not fund_reasons: fund_reasons.append("الوضع المالي مستقر")

        return {
            "recommendation": recommendation, "color": color, "strategy": strategy,
            "tech_score": tech_score, "fund_score": fund_score,
            "tech_reasons": tech_reasons, "fund_reasons": fund_reasons, "trend": trend
        }
    except Exception as e:
        return {"recommendation": "خطأ", "color": "gray", "strategy": str(e), "tech_reasons": [], "fund_reasons": []}

# ============================================================
# 🚀 الجزء الثاني: الذكاء الاستراتيجي للمحفظة (إضافات جديدة)
# (Portfolio Intelligence & Risk Management)
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    """
    حساب درجة مخاطرة المحفظة (0 - 100)
    0 = آمن جداً (كاش) | 100 = مخاطرة قصوى
    """
    try:
        if trades_df.empty: return 0
        
        # 1. مخاطرة التركيز (Concentration Risk)
        open_trades = trades_df[trades_df['status'] == 'Open']
        if open_trades.empty: return 0
        
        # حساب وزن أكبر سهم في المحفظة
        total_market_val = open_trades['market_value'].sum()
        if total_market_val == 0: return 0
        
        max_asset_weight = (open_trades['market_value'].max() / total_market_val) * 100
        concentration_score = 0
        if max_asset_weight > 50: concentration_score = 30 # عقوبة التركيز العالي
        elif max_asset_weight > 25: concentration_score = 15
        
        # 2. مخاطرة السيولة (Liquidity Risk)
        liquidity_score = 0
        if cash_percent < 5: liquidity_score = 25 # خطر نفاد الكاش
        elif cash_percent < 15: liquidity_score = 10
        
        # 3. مخاطرة التذبذب (Volatility - Estimated based on Strategy)
        strategy_score = 0
        spec_ratio = len(open_trades[open_trades['strategy'] == 'مضاربة']) / len(open_trades)
        strategy_score = spec_ratio * 30 # المضاربة تزيد المخاطرة
        
        # 4. حالة السوق (Market Sentiment Penalty)
        market_penalty = 0
        try:
            _, tasi_chg = get_tasi_data()
            if tasi_chg < -1.5: market_penalty = 15 # السوق نازل بقوة
        except: pass

        total_risk = concentration_score + liquidity_score + strategy_score + market_penalty
        return min(round(total_risk, 1), 100)
        
    except Exception:
        return 50 # درجة محايدة عند الخطأ

def run_stress_test(portfolio_value, open_positions_df):
    """
    اختبار تحمل المحفظة (Stress Test)
    محاكاة لانهيار أو صعود السوق وتأثيره على المحفظة.
    """
    try:
        if open_positions_df.empty:
            return {"scenarios": [], "insight": "المحفظة كاش بالكامل، لا يوجد تأثر بالسوق."}
            
        # تقدير معامل بيتا (Beta) تقريبي للمحفظة
        # المضاربة = حساسية عالية (1.2) | الاستثمار = حساسية متوسطة (0.9) | الصكوك = حساسية منخفضة (0.1)
        weighted_beta = 0
        total_val = open_positions_df['market_value'].sum()
        
        if total_val == 0: return {"scenarios": []}

        for _, row in open_positions_df.iterrows():
            w = row['market_value'] / total_val
            if row['asset_type'] == 'Sukuk': b = 0.1
            elif 'مضاربة' in str(row['strategy']): b = 1.2
            else: b = 0.9 # استثمار
            weighted_beta += (w * b)
            
        scenarios = [
            {"name": "انهيار حاد (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
            {"name": "طفرة (+20%)", "market_chg": 0.20, "color": "#047857"},
        ]
        
        results = []
        for s in scenarios:
            impact_pct = s['market_chg'] * weighted_beta
            impact_val = total_val * impact_pct
            results.append({
                "scenario": s['name'],
                "impact_val": impact_val,
                "impact_pct": impact_pct * 100,
                "color": s['color']
            })
            
        insight = ""
        if weighted_beta > 1.1: insight = "⚠️ المحفظة عالية التذبذب وتتأثر بالسوق بقوة (Beta > 1.1)."
        elif weighted_beta < 0.5: insight = "🛡️ المحفظة دفاعية ومستقرة أمام تقلبات السوق."
        else: insight = "⚖️ المحفظة متوازنة وتتحرك بتناغم مع السوق."
        
        return {"scenarios": results, "insight": insight}

    except Exception as e:
        return {"scenarios": [], "insight": "تعذر إجراء اختبار التحمل."}

def generate_rebalancing_suggestions(trades_df, cash_pct):
    """
    محرك التوصيات لإعادة التوازن (Auto Rebalancing)
    """
    suggestions = []
    
    try:
        # 1. فحص الكاش
        if cash_pct < 5:
            suggestions.append(("priority", "🚨 السيولة منخفضة جداً (أقل من 5%). يفضل بيع جزء من الأسهم الرابحة لتوفير سيولة للطوارئ."))
        elif cash_pct > 60:
            suggestions.append(("info", "💡 السيولة عالية (>60%). ابحث عن فرص استثمارية لزيادة العائد."))
            
        if trades_df.empty: return suggestions
        
        open_trades = trades_df[trades_df['status'] == 'Open']
        if open_trades.empty: return suggestions
        
        # 2. فحص الأداء الفردي
        for _, row in open_trades.iterrows():
            gain_pct = row.get('gain_pct', 0)
            symbol = row['symbol']
            name = row.get('company_name', symbol)
            
            # جني أرباح
            if gain_pct > 20:
                suggestions.append(("success", f"💰 **{name}**: حقق ربحاً ممتازاً (+{gain_pct:.1f}%). فكر في جني جزء من الأرباح."))
            
            # وقف خسارة
            if gain_pct < -10:
                suggestions.append(("danger", f"🛑 **{name}**: الخسارة تجاوزت -10%. راجع أسباب الاحتفاظ أو فكر في التفعيل وقف الخسارة."))
        
        # 3. فحص التوزيع القطاعي
        sector_counts = open_trades['sector'].value_counts()
        if not sector_counts.empty:
            top_sector = sector_counts.index[0]
            count = sector_counts.iloc[0]
            if count > 3 and (count / len(open_trades)) > 0.5:
                suggestions.append(("warning", f"⚠️ تركيز عالي في قطاع **{top_sector}**. يفضل التنويع في قطاعات أخرى لتقليل المخاطرة."))

    except Exception: pass
    
    if not suggestions:
        suggestions.append(("success", "✅ وضع المحفظة متوازن، لا توجد إجراءات عاجلة."))
        
    return suggestions
