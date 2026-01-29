import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🕯️ الجزء الأول: تحليل الشموع المتقدم (Advanced Patterns)
# ============================================================
def _detect_advanced_patterns(df):
    """
    اكتشاف النماذج المركبة (نجمة الصباح، المساء، الحرامي، الابتلاع)
    """
    if df is None or len(df) < 5: return 0, []
    
    score = 0
    patterns = []
    
    # تعريف الشموع الثلاث الأخيرة
    c1 = df.iloc[-3] # قبل قبل الأخيرة
    c2 = df.iloc[-2] # السابقة
    c3 = df.iloc[-1] # الحالية
    
    # أحجام الأجسام
    body1 = abs(c1['Close'] - c1['Open'])
    body2 = abs(c2['Close'] - c2['Open'])
    body3 = abs(c3['Close'] - c3['Open'])
    
    # تحديد الاتجاهات (Colors)
    is_c1_red = c1['Close'] < c1['Open']
    is_c1_green = c1['Close'] > c1['Open']
    is_c2_red = c2['Close'] < c2['Open']
    is_c2_green = c2['Close'] > c2['Open']
    is_c3_green = c3['Close'] > c3['Open']
    is_c3_red = c3['Close'] < c3['Open']
    
    # 1. نموذج نجمة الصباح (Morning Star) - إيجابي قوي
    # (هبوط أحمر > حيرة صغير > صعود أخضر يغلق فوق المنتصف)
    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1['Open'] - (body1 / 2)
        if c3['Close'] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح (Morning Star) - إشارة انعكاس إيجابية قوية")

    # 2. نموذج نجمة المساء (Evening Star) - سلبي قوي
    # (صعود أخضر > حيرة صغير > هبوط أحمر يغلق تحت المنتصف)
    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1['Open'] + (body1 / 2)
        if c3['Close'] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء (Evening Star) - إشارة خروج سلبية")

    # 3. نموذج الحرامي (Harami) - توقف الاتجاه
    # (شمعة كبيرة تحتضن شمعة صغيرة بعدها)
    if is_c2_red and is_c3_green and c3['Open'] > c2['Close'] and c3['Close'] < c2['Open']:
        score += 2
        patterns.append("🤰 الحرامي الشرائي (Bullish Harami) - ضعف الزخم الهابط")

    # 4. نموذج الابتلاع (Engulfing) - (تمت إضافته لضمان عدم فقدان الميزات القديمة)
    # (شمعة صغيرة تليها شمعة كبيرة تبتلعها بالكامل)
    if is_c2_red and is_c3_green and c3['Open'] < c2['Close'] and c3['Close'] > c2['Open']:
        score += 2
        patterns.append("🔥 الابتلاع الشرائي (Bullish Engulfing) - سيطرة المشترين")
        
    return score, patterns

# ============================================================
# 📈 الجزء الثاني: هيكلية السوق (Market Structure)
# ============================================================
def _analyze_market_structure(df):
    """
    تحليل القمم والقيعان (Breakouts & Breakdowns)
    """
    if df is None or len(df) < 30: return 0, []
    
    score = 0
    obs = []
    
    curr_price = df['Close'].iloc[-1]
    
    # تحديد القمم والقيعان (نتجاهل آخر يومين للتأكيد)
    last_peak = df['High'].iloc[-25:-2].max()
    last_valley = df['Low'].iloc[-25:-2].min()
    
    # استراتيجية الاختراق
    if curr_price > last_peak:
        score += 3
        obs.append(f"🚀 اختراق قمة سابقة ({last_peak:.2f}) - إشارة دخول صريحة")
    elif curr_price < last_valley:
        score -= 3
        obs.append(f"⚠️ كسر قاع سابق ({last_valley:.2f}) - إشارة خروج (وقف خسارة)")
    else:
        # السعر داخل النطاق
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
                score -= 1 # عقوبة طفيفة للتذبذب العرضي الممل
                obs.append("مسار عرضي (تذبذب)")
            
    return score, obs

# ============================================================
# 💰 الجزء الثالث: القواعد المالية الذهبية
# ============================================================
def _analyze_financial_golden_rules(symbol):
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except:
        return 0, [], {}

    score = 0
    obs = []
    
    try:
        # 1. جودة الأرباح والملاءة (Piotroski)
        piotroski = metrics.get('Piotroski_Score', 0)
        if piotroski >= 7:
            score += 3
            obs.append("💎 أساسيات قوية جداً (جودة أرباح وملاءة عالية)")
        elif piotroski <= 3:
            score -= 3
            obs.append("❌ تحذير: الشركة هشة مالياً")
            
        # 2. التقييم المالي (Graham)
        fv = metrics.get('Fair_Value_Graham', 0)
        rating = metrics.get('Rating', '')
        if fv and fv > 0 and ("قوي" in str(rating) or "جيد" in str(rating)):
             score += 2
             obs.append("✅ السهم يتداول عند تقييم مالي عادل")

        # 3. الكاش التشغيلي (القاعدة الذهبية)
        ops_str = metrics.get('Opinions', '')
        if "سالب" in ops_str and ("تشغيلي" in ops_str or "نقد" in ops_str):
            score -= 4 
            obs.append("⚠️ خطر: التدفق النقدي التشغيلي سالب (الشركة تنزف كاش)")

    except: pass
    return score, obs, metrics

# ============================================================
# 🧠 المحرك المركزي (The Master Brain)
# ============================================================
def generate_ai_report(symbol):
    try:
        # 1. جلب البيانات (6 أشهر للهيكلية)
        df = get_chart_history(symbol, period='6mo') 
        
        # 2. التحليلات المتقدمة
        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)
        
        # 3. التحليل الكلاسيكي (تأكيد)
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        
        # 4. التجميع
        tech_score = s_candle + s_struct + s_vsa
        fund_score = s_fund
        total_score = tech_score + fund_score
        
        # 5. القرار
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

        tech_reasons = o_struct + o_candle + o_vsa
        fund_reasons = o_fund
        
        if not tech_reasons: tech_reasons.append("حركة السعر طبيعية")
        if not fund_reasons: fund_reasons.append("المؤشرات المالية طبيعية")

        return {
            "recommendation": rec, "color": clr, "strategy": strat,
            "tech_score": tech_score, "fund_score": fund_score,
            "tech_reasons": tech_reasons, "fund_reasons": fund_reasons,
            "trend": "صاعد" if s_struct > 0 else "هابط"
        }

    except Exception as e:
        return {
            "recommendation": "غير متاح", "color": "#6c757d", "strategy": "نقص بيانات",
            "tech_reasons": [], "fund_reasons": []
        }

# ============================================================
# 🛡️ الجزء الرابع: ذكاء المحفظة (Full Logic Preserved)
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    try:
        if trades_df.empty: return 0
        open_trades = trades_df[trades_df['status'] == 'Open']
        if open_trades.empty: return 0
        
        total_market_val = open_trades['market_value'].sum()
        if total_market_val == 0: return 0
        
        # 1. التركيز
        max_asset_weight = (open_trades['market_value'].max() / total_market_val) * 100
        concentration_score = 30 if max_asset_weight > 50 else (15 if max_asset_weight > 25 else 0)
        
        # 2. السيولة
        liquidity_score = 25 if cash_percent < 5 else (10 if cash_percent < 15 else 0)
        
        # 3. المضاربة
        strategy_score = 0
        try:
            spec_ratio = len(open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة', na=False)]) / len(open_trades)
            strategy_score = spec_ratio * 30 
        except: pass

        return min(round(concentration_score + liquidity_score + strategy_score, 1), 100)
    except: return 50

def run_stress_test(portfolio_value, open_positions_df):
    try:
        if open_positions_df.empty: return {"scenarios": [], "insight": "المحفظة كاش."}
            
        weighted_beta = 0
        total_val = open_positions_df['market_value'].sum()
        if total_val == 0: return {"scenarios": []}

        for _, row in open_positions_df.iterrows():
            w = row['market_value'] / total_val
            if row.get('asset_type') == 'Sukuk': b = 0.1
            elif 'مضاربة' in str(row.get('strategy', '')): b = 1.2
            else: b = 0.9 
            weighted_beta += (w * b)
            
        scenarios = [
            {"name": "انهيار (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
            {"name": "طفرة (+20%)", "market_chg": 0.20, "color": "#047857"},
        ]
        
        results = []
        for s in scenarios:
            impact_pct = s['market_chg'] * weighted_beta
            results.append({
                "scenario": s['name'],
                "impact_pct": impact_pct * 100,
                "color": s['color']
            })
            
        insight = "المحفظة عالية التذبذب" if weighted_beta > 1.1 else "المحفظة متوازنة"
        return {"scenarios": results, "insight": insight}
    except: return {"scenarios": [], "insight": "غير متاح"}

def generate_rebalancing_suggestions(trades_df, cash_pct):
    suggestions = []
    try:
        if cash_pct < 5:
            suggestions.append(("priority", "🚨 السيولة منخفضة جداً (< 5%)"))
        if not trades_df.empty:
            open_trades = trades_df[trades_df['status'] == 'Open']
            for _, row in open_trades.iterrows():
                if row.get('gain_pct', 0) < -10:
                    suggestions.append(("danger", f"🛑 خسارة تجاوزت -10% في {row['symbol']}"))
    except: pass
    return suggestions

def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 20: return 0, []
    score = 0; obs = []
    curr = df.iloc[-1]
    avg_vol = df['Volume'].iloc[-20:].mean()
    if curr['Volume'] > avg_vol * 1.5:
        range_size = curr['High'] - curr['Low']
        avg_range = (df['High'] - df['Low']).iloc[-20:].mean()
        if range_size < avg_range * 0.8:
            obs.append("VSA: فوليوم عالي بمدى ضيق (احتمال تلاعب)")
    return score, obs
