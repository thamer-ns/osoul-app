import pandas as pd
import numpy as np
from market_data import get_chart_history, get_tasi_data
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 📚 المحرك المعرفي: مبني على مراجع التحليل الفني والمالي
# ============================================================

def _analyze_vsa_art_of_trading(df):
    """
    تحليل الحجم والمدى (Volume Spread Analysis)
    المصدر: كتاب فن التداول (توم ويليامز)
    الهدف: كشف تحركات "الأموال الذكية" (Smart Money)
    """
    if df is None or len(df) < 20: return 0, []
    
    score = 0
    obs = []
    
    # تجهيز البيانات
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # حساب المتوسطات
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    avg_spread = (df['High'] - df['Low']).rolling(20).mean().iloc[-1]
    
    current_spread = curr['High'] - curr['Low']
    current_vol = curr['Volume']
    
    # 1. إشارة "الجهد بلا نتيجة" (Effort vs Result)
    if current_vol > avg_vol * 1.5 and current_spread < avg_spread * 0.8:
        if curr['Close'] > prev['Close']: 
            score -= 2
            obs.append("VSA: جهد شرائي عالي بمدى ضيق (إشارة تصريف محتملة)")
        else: 
            score += 2
            obs.append("VSA: جهد بيعي عالي بمدى ضيق (إشارة تجميع/امتصاص)")

    # 2. اختبار العرض (Testing for Supply)
    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    body_size = abs(curr['Close'] - curr['Open'])
    
    if lower_wick > body_size * 2 and current_vol < avg_vol:
        score += 2
        obs.append("VSA: نجاح اختبار العرض (No Supply) - إشارة إيجابية")

    # 3. ذروة الشراء (Buying Climax)
    upper_wick = curr['High'] - max(curr['Close'], curr['Open'])
    if current_vol > avg_vol * 3 and upper_wick > body_size:
        score -= 3
        obs.append("VSA: ذروة شراء (Buying Climax) - الحذر من الانعكاس")

    return score, obs

def _analyze_dow_theory_murphy(df):
    """
    تحليل الاتجاه العام
    المصدر: كتاب جون ميرفي للتحليل الفني
    """
    if df is None or len(df) < 200: return 0, [], "غير مؤكد"
    
    score = 0
    obs = []
    trend_status = "عرضي"
    
    last_close = df['Close'].iloc[-1]
    sma_50 = df['Close'].rolling(50).mean().iloc[-1]
    sma_200 = df['Close'].rolling(200).mean().iloc[-1]
    
    # 1. تحديد الاتجاه الرئيسي (Primary Trend)
    if last_close > sma_200:
        if sma_50 > sma_200:
            score += 3
            trend_status = "صاعد قوي (Bull Market)"
            obs.append("السعر والمتوسطات في ترتيب صاعد مثالي (نظرية داو)")
        else:
            score += 1
            trend_status = "صاعد ضعيف"
            obs.append("السعر فوق متوسط 200 يوم لكن الزخم يضعف")
    else:
        score -= 2
        trend_status = "هابط (Bear Market)"
        obs.append("السعر يتداول تحت متوسط 200 يوم (سلبية رئيسية)")

    # 2. الانفراجات (Divergence) - باستخدام RSI
    try:
        rsi = _calculate_rsi(df)
        if df['Close'].iloc[-1] > df['Close'].iloc[-10] and rsi.iloc[-1] < rsi.iloc[-10]:
            score -= 1
            obs.append("انفراج سلبي (Bearish Divergence): السعر يصعد والعزم يهبط")
    except: pass

    return score, obs, trend_status

def _detect_candlestick_patterns(df):
    """
    النماذج اليابانية
    المصدر: كتب الشموع اليابانية المرفقة
    """
    if df is None or len(df) < 5: return 0, []
    score = 0
    patterns = []
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    body = abs(curr['Close'] - curr['Open'])
    upper_wick = curr['High'] - max(curr['Close'], curr['Open'])
    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        score += 1
        patterns.append("شمعة المطرقة (Hammer) - انعكاسية إيجابية")
        
    if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']: 
        if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']: 
            score += 2
            patterns.append("الابتلاع الشرائي (Bullish Engulfing) - إشارة دخول قوية")
            
    if upper_wick > body * 2 and lower_wick < body * 0.5:
        score -= 1
        patterns.append("شمعة الشهاب (Shooting Star) - انعكاسية سلبية")

    return score, patterns

def _analyze_deep_financials(symbol):
    """
    التحليل المالي العميق
    المصدر: كتب القوائم المالية (تحليل جودة الأرباح والسيولة)
    """
    try:
        metrics = get_advanced_fundamental_ratios(symbol) 
        # حماية ضد القيم الفارغة
        if not metrics:
            return 0, ["لا توجد بيانات مالية كافية"], {}
            
        score = 0
        obs = []
        
        # 1. متانة المركز المالي (Piotroski F-Score)
        f_score = metrics.get('Piotroski_Score', 0)
        if f_score >= 8:
            score += 3
            obs.append(f"مركز مالي ممتاز جداً (F-Score {f_score}/9)")
        elif f_score <= 3:
            score -= 3
            obs.append("تحذير: ضعف في الكفاءة التشغيلية أو تزايد الديون")
            
        # 2. القيمة العادلة (Ben Graham)
        fv = metrics.get('Fair_Value_Graham')
        price = metrics.get('Current_Price', 0)
        
        if fv and fv > 0 and price > 0:
            if price < fv * 0.7: 
                score += 3
                obs.append(f"فرصة قيمة: السعر الحالي أقل بكثير من القيمة العادلة ({fv:.2f})")
            elif price > fv * 1.4:
                score -= 2
                obs.append("السعر متضخم مقارنة بالقيمة العادلة")

        # 3. جودة الأرباح (Quality of Earnings)
        if "تدفق نقدي تشغيلي سالب" in metrics.get('Opinions', ''):
            score -= 2
            obs.append("جودة أرباح منخفضة (النقد التشغيلي سالب)")

        return score, obs, metrics
    except Exception as e:
        return 0, [f"خطأ في التحليل المالي: {str(e)}"], {}

def _calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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
        
        open_trades = trades_df[trades_df['status'] == 'Open']
        if open_trades.empty: return 0
        
        total_market_val = open_trades['market_value'].sum()
        if total_market_val == 0: return 0
        
        # 1. مخاطرة التركيز
        max_asset_weight = (open_trades['market_value'].max() / total_market_val) * 100
        concentration_score = 30 if max_asset_weight > 50 else (15 if max_asset_weight > 25 else 0)
        
        # 2. مخاطرة السيولة
        liquidity_score = 25 if cash_percent < 5 else (10 if cash_percent < 15 else 0)
        
        # 3. مخاطرة التذبذب
        strategy_score = 0
        try:
            spec_ratio = len(open_trades[open_trades['strategy'].str.contains('مضاربة', na=False)]) / len(open_trades)
            strategy_score = spec_ratio * 30
        except: pass
        
        # 4. حالة السوق
        market_penalty = 0
        try:
            _, tasi_chg = get_tasi_data()
            if tasi_chg < -1.5: market_penalty = 15
        except: pass

        total_risk = concentration_score + liquidity_score + strategy_score + market_penalty
        return min(round(total_risk, 1), 100)
        
    except Exception:
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
            if row.get('asset_type') == 'Sukuk': b = 0.1
            elif 'مضاربة' in str(row.get('strategy', '')): b = 1.2
            else: b = 0.9
            weighted_beta += (w * b)
            
        scenarios = [
            {"name": "انهيار (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
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
            
        insight = "المحفظة متوازنة"
        if weighted_beta > 1.1: insight = "المحفظة عالية التذبذب"
        
        return {"scenarios": results, "insight": insight}

    except Exception:
        return {"scenarios": [], "insight": "غير متاح"}

def generate_rebalancing_suggestions(trades_df, cash_pct):
    suggestions = []
    try:
        if cash_pct < 5:
            suggestions.append(("priority", "السيولة منخفضة جداً (< 5%)"))
        
        if not trades_df.empty:
            open_trades = trades_df[trades_df['status'] == 'Open']
            for _, row in open_trades.iterrows():
                if row.get('gain_pct', 0) < -10:
                    suggestions.append(("danger", f"خسارة تجاوزت -10% في {row['symbol']}"))
    except: pass
    return suggestions

# ============================================================
# المعالج المركزي (Main Generator)
# ============================================================

def generate_ai_report(symbol):
    """
    المعالج المركزي: يجمع التحليلات ويصدر التوصية
    """
    try:
        # جلب البيانات
        df = get_chart_history(symbol, period='2y')
        
        # تشغيل المحركات
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        s_dow, o_dow, trend = _analyze_dow_theory_murphy(df)
        s_can, o_can = _detect_candlestick_patterns(df)
        
        # تشغيل التحليل المالي مع حماية
        s_fun, o_fun, m_fun = 0, [], {}
        try:
            s_fun, o_fun, m_fun = _analyze_deep_financials(symbol)
        except:
            o_fun.append("بيانات مالية غير مكتملة")

        # حساب النتيجة النهائية
        tech_score = s_vsa + s_dow + s_can
        fund_score = s_fun
        total_score = tech_score + fund_score
        
        # صياغة التوصية
        recommendation = "محايد / مراقبة"
        color = "#6c757d" # Gray
        strategy = "تضارب الإشارات الفنية والمالية. يفضل الانتظار."
        
        if total_score >= 7:
            recommendation = "💎 استثمار ذهبي (Strong Buy)"
            color = "#198754" # Green
            strategy = "توافق ممتاز بين القوة المالية والإشارات الفنية."
        elif total_score >= 4:
            recommendation = "✅ شراء / تجميع"
            color = "#28a745"
            strategy = "الاتجاه العام إيجابي والشركة مستقرة."
        elif total_score <= -4:
            recommendation = "⛔ خروج / تجنب"
            color = "#dc3545" # Red
            strategy = "إشارات سلبية متعددة (تصريف فني أو ضعف مالي)."
        elif tech_score >= 3 and fund_score < 0:
            recommendation = "⚡ مضاربة بحذر"
            color = "#ffc107" # Yellow
            strategy = "جيد فنياً للمضاربة السريعة، لكن مالياً غير آمن."
        elif fund_score >= 4 and tech_score < 0:
            recommendation = "📉 استثمار قيمة"
            color = "#0d6efd" # Blue
            strategy = "سعر هابط لشركة قوية."

        # تجميع الملاحظات
        tech_reasons = o_dow + o_vsa + o_can
        fund_reasons = o_fun
        
        if not tech_reasons: tech_reasons.append("لا توجد أنماط فنية مميزة حالياً")
        if not fund_reasons: fund_reasons.append("الوضع المالي طبيعي ومستقر")

        return {
            "recommendation": recommendation,
            "color": color,
            "strategy": strategy,
            "tech_score": tech_score,
            "fund_score": fund_score,
            "tech_reasons": tech_reasons,
            "fund_reasons": fund_reasons,
            "trend": trend
        }
    except Exception as e:
        # Fallback في حالة الخطأ التام
        return {
            "recommendation": "خطأ في التحليل",
            "color": "#6c757d",
            "strategy": f"حدث خطأ أثناء المعالجة: {str(e)}",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "غير معروف"
        }
