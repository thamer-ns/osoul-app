import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🕯️ الجزء الأول: تحليل الشموع المتقدم (من كتب الشموع المرفقة)
# ============================================================

def _detect_advanced_patterns(df):
    """
    اكتشاف النماذج المركبة (نجمة الصباح، المساء، الحرامي)
    المصدر: ملف 'شرح شمعة نجمة الصباح والمساء.pdf'
    """
    if df is None or len(df) < 5: return 0, []
    
    score = 0
    patterns = []
    
    # تعريف الشموع الثلاث الأخيرة
    c1 = df.iloc[-3] # الشمعة قبل قبل الأخيرة
    c2 = df.iloc[-2] # الشمعة السابقة (النجمة)
    c3 = df.iloc[-1] # الشمعة الحالية
    
    # حسابات مساعدة لأحجام الشموع
    body1 = abs(c1['Close'] - c1['Open'])
    body2 = abs(c2['Close'] - c2['Open'])
    body3 = abs(c3['Close'] - c3['Open'])
    
    is_c1_red = c1['Close'] < c1['Open']
    is_c1_green = c1['Close'] > c1['Open']
    is_c3_green = c3['Close'] > c3['Open']
    is_c3_red = c3['Close'] < c3['Open']
    
    # 1. نموذج نجمة الصباح (Morning Star) - إشارة انعكاس إيجابية قوية
    # شروط: شمعة حمراء طويلة -> شمعة صغيرة (حيرة) -> شمعة خضراء تغلق فوق منتصف الأولى
    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1['Open'] - (body1 / 2)
        if c3['Close'] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح (Morning Star) - إشارة انعكاس إيجابية قوية")

    # 2. نموذج نجمة المساء (Evening Star) - إشارة سلبية
    # شروط: شمعة خضراء طويلة -> شمعة صغيرة -> شمعة حمراء تغلق تحت منتصف الأولى
    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1['Open'] + (body1 / 2)
        if c3['Close'] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء (Evening Star) - إشارة خروج سلبية")

    # 3. نموذج الحرامي الشرائي (Bullish Harami)
    is_c2_red = c2['Close'] < c2['Open']
    if is_c2_red and is_c3_green and c3['Open'] > c2['Close'] and c3['Close'] < c2['Open']:
        score += 2
        patterns.append("🤰 نموذج الحرامي الشرائي (Bullish Harami) - ضعف الهبوط")
        
    return score, patterns

# ============================================================
# 📈 الجزء الثاني: هيكلية السوق (من ملف القمم والقيعان)
# ============================================================

def _analyze_market_structure(df):
    """
    تحليل القمم والقيعان (Breakouts & Breakdowns)
    المصدر: ملف 'شرح الدخول والخروج على القمم والقيعان.pdf'
    """
    if df is None or len(df) < 30: return 0, []
    
    score = 0
    obs = []
    
    curr_price = df['Close'].iloc[-1]
    
    # تحديد أعلى قمة وأدنى قاع في آخر 20 يوم (شهر تداول)
    last_peak = df['High'].iloc[-25:-2].max()
    last_valley = df['Low'].iloc[-25:-2].min()
    
    # استراتيجية الاختراق (Breakout Strategy)
    if curr_price > last_peak:
        score += 3
        obs.append(f"🚀 اختراق قمة سابقة ({last_peak:.2f}) - إشارة دخول صريحة (Market Structure Break)")
    elif curr_price < last_valley:
        score -= 3
        obs.append(f"⚠️ كسر قاع سابق ({last_valley:.2f}) - إشارة خروج (وقف خسارة)")
    else:
        # السعر يتذبذب
        range_size = last_peak - last_valley
        if range_size > 0:
            pos = (curr_price - last_valley) / range_size
            if pos > 0.8:
                score += 1
                obs.append("السعر يقترب من اختراق قمة (مراقبة)")
            elif pos < 0.2:
                score -= 1
                obs.append("السعر يقترب من كسر قاع (حذر)")
            
    return score, obs

# ============================================================
# 💰 الجزء الثالث: القواعد المالية الذهبية (من ملفات التحليل المالي)
# ============================================================

def _analyze_financial_golden_rules(symbol):
    """
    تطبيق معايير 'استمارة الفحص' و 'المؤشرات المالية المهمة'
    """
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except:
        return 0, [], {}

    score = 0
    obs = []
    
    try:
        # 1. قاعدة جودة الأرباح (Quality of Earnings)
        ops_str = metrics.get('Opinions', '')
        piotroski = metrics.get('Piotroski_Score', 0)
        
        if piotroski >= 7:
            score += 3
            obs.append("💎 أساسيات قوية جداً (جودة أرباح وملاءة عالية)")
        elif piotroski <= 3:
            score -= 3
            obs.append("❌ تحذير: الشركة هشة مالياً")
            
        # 2. مكرر الربحية وقيمة النمو
        fv = metrics.get('Fair_Value_Graham')
        rating = metrics.get('Rating', '')
        
        if fv and fv > 0:
             if "قوي" in str(rating) or "جيد" in str(rating):
                 score += 2
                 obs.append("✅ السهم يتداول عند تقييم مالي عادل")

        # 3. الكاش التشغيلي (من الملاحظات النصية)
        if "سالب" in ops_str and "تشغيلي" in ops_str:
            score -= 4 
            obs.append("⚠️ خطر: التدفق النقدي التشغيلي سالب")

    except: pass

    return score, obs, metrics

# ============================================================
# 🧠 المحرك المركزي لتحليل الأسهم (The Master Brain)
# ============================================================

def generate_ai_report(symbol):
    try:
        # 1. جلب البيانات التاريخية
        df = get_chart_history(symbol, period='6mo') 
        
        # 2. تشغيل الوحدات التحليلية المتقدمة
        s_candle, o_candle = _detect_advanced_patterns(df) 
        s_struct, o_struct = _analyze_market_structure(df) 
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)
        
        # 3. التحليلات الكلاسيكية (للتأكيد فقط)
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        
        # 4. التجميع النهائي للنقاط
        tech_score = s_candle + s_struct + s_vsa
        fund_score = s_fund
        total_score = tech_score + fund_score
        
        # 5. صناعة القرار
        recommendation = "محايد / مراقبة"
        color = "#6c757d"
        strategy = "السعر في منطقة حيرة. انتظر إشارة أوضح."

        if total_score >= 7:
            recommendation = "💎 فرصة ماسية (Strong Buy)"
            color = "#198754"
            strategy = "توافق مذهل: اختراق قمة + نموذج إيجابي + مالية قوية."
        elif total_score >= 4:
            recommendation = "✅ شراء / تجميع"
            color = "#28a745"
            strategy = "الإشارات الإيجابية تغلب. الهيكلية صاعدة."
        elif total_score <= -4:
            recommendation = "⛔ خروج / وقف خسارة"
            color = "#dc3545"
            strategy = "كسر قاع سابق أو نموذج شموع سلبي. الحفاظ على المال أولى."
        elif tech_score > 3 and fund_score < 0:
            recommendation = "⚡ مضاربة بحذر"
            color = "#ffc107"
            strategy = "فني ممتاز (اختراق) ولكن الشركة ضعيفة مالياً."
        elif fund_score > 4 and tech_score < 0:
            recommendation = "📉 استثمار قيمة"
            color = "#0d6efd"
            strategy = "السعر يهبط لكن الشركة قوية جداً."

        tech_reasons = o_struct + o_candle + o_vsa
        fund_reasons = o_fund
        
        if not tech_reasons: tech_reasons.append("حركة السعر طبيعية")
        if not fund_reasons: fund_reasons.append("المؤشرات المالية طبيعية")

        return {
            "recommendation": recommendation,
            "color": color,
            "strategy": strategy,
            "tech_score": tech_score,
            "fund_score": fund_score,
            "tech_reasons": tech_reasons,
            "fund_reasons": fund_reasons,
            "trend": "صاعد" if s_struct > 0 else "هابط"
        }

    except Exception as e:
        return {
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص في البيانات",
            "tech_reasons": [],
            "fund_reasons": []
        }

# ============================================================
# 🛡️ الجزء الرابع: ذكاء المحفظة (Portfolio Intelligence)
# هذا الجزء هو الذي كان ناقصاً وتسبب في مشاكل الصفحة الرئيسية
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    """
    حساب درجة مخاطرة المحفظة (0 - 100)
    """
    try:
        if trades_df.empty: return 0
        
        # 1. مخاطرة التركيز
        open_trades = trades_df[trades_df['status'] == 'Open']
        if open_trades.empty: return 0
        total_market_val = open_trades['market_value'].sum()
        if total_market_val == 0: return 0
        
        max_asset_weight = (open_trades['market_value'].max() / total_market_val) * 100
        concentration_score = 30 if max_asset_weight > 50 else (15 if max_asset_weight > 25 else 0)
        
        # 2. مخاطرة السيولة
        liquidity_score = 25 if cash_percent < 5 else (10 if cash_percent < 15 else 0)
        
        # 3. المضاربة
        strategy_score = 0
        try:
            spec_ratio = len(open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة', na=False)]) / len(open_trades)
            strategy_score = spec_ratio * 30 
        except: pass

        total_risk = concentration_score + liquidity_score + strategy_score
        return min(round(total_risk, 1), 100)
    except:
        return 50

def run_stress_test(portfolio_value, open_positions_df):
    """
    اختبار تحمل المحفظة (Stress Test)
    """
    try:
        if open_positions_df.empty:
            return {"scenarios": [], "insight": "المحفظة كاش بالكامل."}
            
        weighted_beta = 0
        total_val = open_positions_df['market_value'].sum()
        if total_val == 0: return {"scenarios": []}

        for _, row in open_positions_df.iterrows():
            w = row['market_value'] / total_val
            # تقدير البيتا حسب نوع الأصل
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
            impact_val = total_val * impact_pct
            results.append({
                "scenario": s['name'],
                "impact_pct": impact_pct * 100,
                "color": s['color']
            })
            
        insight = "المحفظة عالية التذبذب" if weighted_beta > 1.1 else "المحفظة متوازنة"
        return {"scenarios": results, "insight": insight}

    except:
        return {"scenarios": [], "insight": "غير متاح"}

def generate_rebalancing_suggestions(trades_df, cash_pct):
    """
    محرك التوصيات لإعادة التوازن
    """
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

# --- دالة VSA القديمة للتوافق ---
def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 20: return 0, []
    score = 0; obs = []
    curr = df.iloc[-1]
    avg_vol = df['Volume'].iloc[-20:].mean()
    if curr['Volume'] > avg_vol * 1.5:
        range_size = curr['High'] - curr['Low']
        avg_range = (df['High'] - df['Low']).iloc[-20:].mean()
        if range_size < avg_range * 0.8:
            obs.append("VSA: فوليوم عالي جداً بمدى ضيق (احتمال تلاعب)")
    return score, obs
