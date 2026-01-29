import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🏛️ الجزء الأول: المحرك المعرفي (تحليل الأسهم الفردي)
# ============================================================

def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 20: return 0, []
    score = 0; obs = []
    curr = df.iloc[-1]; prev = df.iloc[-2]
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    current_vol = curr['Volume']
    
    # جهد عالي مدى ضيق
    spread = curr['High'] - curr['Low']
    avg_spread = (df['High'] - df['Low']).rolling(20).mean().iloc[-1]
    
    if current_vol > avg_vol * 1.5 and spread < avg_spread * 0.8:
        if curr['Close'] > prev['Close']: 
            score -= 2; obs.append("VSA: جهد شرائي عالي بمدى ضيق (تصريف محتمل)")
        else: 
            score += 2; obs.append("VSA: جهد بيعي عالي بمدى ضيق (تجميع محتمل)")
            
    return score, obs

def _analyze_dow_theory(df):
    if df is None or len(df) < 200: return 0, [], "غير مؤكد"
    score = 0; obs = []
    close = df['Close'].iloc[-1]
    sma200 = df['Close'].rolling(200).mean().iloc[-1]
    
    if close > sma200:
        score += 3; trend = "صاعد (Bull)"
        obs.append("السعر فوق متوسط 200 يوم (إيجابية)")
    else:
        score -= 2; trend = "هابط (Bear)"
        obs.append("السعر تحت متوسط 200 يوم (سلبية)")
        
    return score, obs, trend

def _detect_patterns(df):
    if df is None or len(df) < 5: return 0, []
    score = 0; patterns = []
    curr = df.iloc[-1]; prev = df.iloc[-2]
    
    # الابتلاع الشرائي
    if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
        if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
            score += 2; patterns.append("نموذج ابتلاع شرائي (إيجابي)")
            
    return score, patterns

def generate_ai_report(symbol):
    """
    توليد التقرير الشامل للسهم
    """
    try:
        # جلب البيانات
        df = get_chart_history(symbol, period='2y')
        fin_metrics = get_advanced_fundamental_ratios(symbol)
        
        # تشغيل التحليلات
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        s_dow, o_dow, trend = _analyze_dow_theory(df)
        s_pat, o_pat = _detect_patterns(df)
        
        # التحليل المالي المبسط للمستشار
        s_fund = 0; o_fund = []
        if fin_metrics.get('Piotroski_Score', 0) >= 6:
            s_fund += 3; o_fund.append("مركز مالي قوي (Piotroski عالي)")
        elif fin_metrics.get('Piotroski_Score', 0) <= 3:
            s_fund -= 3; o_fund.append("ضعف في المركز المالي")
            
        # التجميع
        tech_score = s_vsa + s_dow + s_pat
        total = tech_score + s_fund
        
        # القرار
        if total >= 6: rec = "💎 فرصة ذهبية"; clr = "#198754"; strat = "توافق مالي وفني ممتاز"
        elif total >= 3: rec = "✅ شراء / احتفاظ"; clr = "#28a745"; strat = "اتجاه إيجابي عام"
        elif total <= -3: rec = "⛔ خروج / حذر"; clr = "#dc3545"; strat = "إشارات سلبية"
        else: rec = "⚖️ مراقبة"; clr = "#6c757d"; strat = "تضارب الإشارات"
        
        return {
            "recommendation": rec, "color": clr, "strategy": strat,
            "tech_reasons": o_dow + o_vsa + o_pat,
            "fund_reasons": o_fund
        }
    except:
        return {
            "recommendation": "غير متاح", "color": "#6c757d", 
            "strategy": "نقص في البيانات", "tech_reasons": [], "fund_reasons": []
        }

# ============================================================
# 🚀 الجزء الثاني: الذكاء الاستراتيجي للمحفظة
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    """حساب درجة المخاطرة (0-100)"""
    try:
        if trades_df.empty: return 0
        
        # 1. مخاطرة التركيز
        open_trades = trades_df[trades_df['status'] == 'Open']
        if open_trades.empty: return 0
        total_val = open_trades['market_value'].sum()
        max_asset = open_trades['market_value'].max()
        conc_score = (max_asset / total_val * 100) if total_val > 0 else 0
        
        # 2. مخاطرة السيولة
        liq_penalty = 20 if cash_percent < 5 else 0
        
        # 3. المضاربة
        spec_count = len(open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة')])
        spec_penalty = spec_count * 5
        
        final_score = (conc_score * 0.5) + liq_penalty + spec_penalty
        return min(int(final_score), 100)
    except: return 50

def run_stress_test(portfolio_val, open_pos):
    """اختبار تحمل المحفظة"""
    if open_pos.empty: return {"scenarios": [], "insight": "محفظة كاش"}
    
    total_market = open_pos['market_value'].sum()
    
    # سيناريوهات بسيطة
    scenarios = [
        {"scenario": "انهيار (-20%)", "impact_pct": -20, "color": "#8B0000"},
        {"scenario": "تصحيح (-10%)", "impact_pct": -10, "color": "#dc3545"},
        {"scenario": "انتعاش (+10%)", "impact_pct": 10, "color": "#28a745"},
        {"scenario": "طفرة (+20%)", "impact_pct": 20, "color": "#198754"}
    ]
    
    # حساب التأثير
    # نفترض بيتا 1.0 للمحفظة للتبسيط (يمكن تطويره لاحقاً)
    for s in scenarios:
        s['impact_val'] = total_market * (s['impact_pct'] / 100)
        
    return {
        "scenarios": scenarios,
        "insight": "هذا اختبار افتراضي بفرض أن المحفظة تتحرك بنفس حركة السوق."
    }

def generate_rebalancing_suggestions(trades, cash_pct):
    suggestions = []
    if cash_pct < 5:
        suggestions.append(('priority', 'السيولة منخفضة جداً (أقل من 5%). فكر في البيع لتوفير الكاش.'))
    if cash_pct > 50:
        suggestions.append(('info', 'لديك سيولة عالية، ابحث عن فرص استثمارية.'))
    return suggestions
