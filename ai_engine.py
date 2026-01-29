import pandas as pd
import numpy as np
from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 📚 المحرك المعرفي: مبني على مراجع التحليل الفني والمالي
# ============================================================

def _analyze_vsa_art_of_trading(df):
    """
    تحليل الحجم والمدى (Volume Spread Analysis)
    المصدر: كتاب فن التداول
    """
    if df is None or len(df) < 20: return 0, []
    
    score = 0
    obs = []
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    
    # 1. جهد عالي بدون نتيجة (High Volume, Small Body) -> انعكاس محتمل
    body_size = abs(curr['Close'] - curr['Open'])
    avg_body = abs(df['Close'] - df['Open']).rolling(20).mean().iloc[-1]
    
    if curr['Volume'] > avg_vol * 1.5 and body_size < avg_body * 0.5:
        if curr['Close'] > prev['Close']: # في قمة
            score -= 2
            obs.append("VSA: جهد شرائي عالي بمدى ضيق (تصريف محتمل)")
        else: # في قاع
            score += 2
            obs.append("VSA: جهد بيعي عالي بمدى ضيق (تجميع محتمل)")

    # 2. اختراق وهمي (Up-thrust)
    # ذيل علوي طويل مع فوليوم عالي وإغلاق منخفض
    upper_wick = curr['High'] - max(curr['Close'], curr['Open'])
    if upper_wick > body_size * 2 and curr['Volume'] > avg_vol:
        score -= 2
        obs.append("VSA: إشارة Up-thrust (محاولة صعود فاشلة)")

    # 3. اختبار الطلب (Test for Supply)
    # نزول ثم إغلاق مرتفع بفوليوم منخفض
    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    if lower_wick > body_size * 2 and curr['Volume'] < avg_vol:
        score += 2
        obs.append("VSA: اختبار ناجح للعرض (No Supply) - إيجابي")

    return score, obs

def _analyze_dow_theory_murphy(df):
    """
    تحليل الاتجاه والقمم والقيعان
    المصدر: كتاب جون ميرفي للتحليل الفني
    """
    if df is None or len(df) < 50: return 0, [], "غير واضح"
    
    score = 0
    obs = []
    
    # تحديد آخر قمتين وآخر قاعين (تقريبي)
    # نستخدم نافذة زمنية لتحديد القمم المحلية
    last_close = df['Close'].iloc[-1]
    sma_50 = df['Close'].rolling(50).mean().iloc[-1]
    sma_200 = df['Close'].rolling(200).mean().iloc[-1]
    
    # 1. المتوسطات المتحركة (أساس الاتجاه)
    if last_close > sma_200:
        score += 2
        trend = "صاعد (سوق ثيران)"
        obs.append("السعر يتداول فوق متوسط 200 يوم (إيجابية طويلة المدى)")
    else:
        score -= 2
        trend = "هابط (سوق دببة)"
        obs.append("السعر يتداول تحت متوسط 200 يوم (سلبية طويلة المدى)")
        
    # 2. التقاطعات (Golden/Death Cross)
    if sma_50 > sma_200:
        score += 1
    elif sma_50 < sma_200:
        score -= 1
        obs.append("تقاطع سلبي للمتوسطات (Death Cross)")

    return score, obs, trend

def _analyze_deep_financials(symbol):
    """
    التحليل المالي العميق (السيولة، النشاط، الربحية)
    المصدر: كتب القوائم المالية وسلسلة التحليل المالي
    """
    metrics, price = get_advanced_fundamental_ratios(symbol)
    score = 0
    obs = []
    
    # استرجاع البيانات المحسوبة
    f_score = metrics.get('Piotroski_Score', 0)
    graham = metrics.get('Fair_Value_Graham', 0)
    
    # 1. تقييم المتانة (F-Score)
    if f_score >= 7:
        score += 3
        obs.append(f"مركز مالي صلب جداً (Piotroski {f_score}/9)")
    elif f_score <= 3:
        score -= 3
        obs.append("تحذير: مؤشرات ضعف مالي أو مشاكل تشغيلية")
        
    # 2. تقييم السعر (Graham)
    if graham and graham > 0:
        discount = ((graham - price) / graham) * 100
        if discount > 20:
            score += 3
            obs.append(f"سعر لقطة: يتداول بخصم {discount:.1f}% عن قيمته العادلة")
        elif discount < -30:
            score -= 2
            obs.append("السعر متضخم مقارنة بالقيمة العادلة")
    
    # 3. توزيعات الأرباح (إن وجدت)
    div_safety = metrics.get('Dividend_Safety', 'N/A')
    if div_safety == "آمنة ومستدامة":
        score += 1
        obs.append("توزيعات الأرباح آمنة ومستدامة")
        
    return score, obs, metrics

def _detect_candlestick_patterns(df):
    """
    النماذج اليابانية الانعكاسية
    المصدر: كتاب الشموع اليابانية
    """
    if df is None or len(df) < 3: return 0, []
    score = 0
    patterns = []
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    body = abs(curr['Close'] - curr['Open'])
    upper_wick = curr['High'] - max(curr['Close'], curr['Open'])
    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    
    # المطرقة (Hammer)
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        score += 1
        patterns.append("شمعة المطرقة (Hammer) - احتمال ارتداد")
        
    # الابتلاع الشرائي
    if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
        if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
            score += 2
            patterns.append("الابتلاع الشرائي (Bullish Engulfing) - إشارة قوية")
            
    return score, patterns

def generate_ai_report(symbol):
    """
    المعالج المركزي: يجمع كل المدارس ويصدر الحكم النهائي
    """
    df = get_chart_history(symbol, period='2y')
    
    # تشغيل المحركات الفرعية
    score_dow, obs_dow, trend = _analyze_dow_theory_murphy(df)
    score_vsa, obs_vsa = _analyze_vsa_art_of_trading(df)
    score_candle, obs_candle = _detect_candlestick_patterns(df)
    score_fund, obs_fund, metrics = _analyze_deep_financials(symbol)
    
    # التجميع النهائي
    total_tech_score = score_dow + score_vsa + score_candle
    total_score = total_tech_score + score_fund
    
    # صناعة القرار
    recommendation = "محايد / مراقبة"
    color = "#6c757d"
    strategy = "تضارب الأدلة الفنية والمالية. يفضل الانتظار لظهور إشارة أوضح."
    
    if total_score >= 7:
        recommendation = "💎 استثمار ذهبي (Strong Buy)"
        color = "#198754"
        strategy = "توافق مذهل بين القوة المالية والاتجاه الفني والسيولة. فرصة نادرة."
    elif total_score >= 4:
        recommendation = "✅ شراء / زيادة كميات"
        color = "#28a745"
        strategy = "السهم إيجابي في الغالب. جيد للتمركز."
    elif total_score <= -4:
        recommendation = "⛔ خروج / وقف خسارة"
        color = "#dc3545"
        strategy = "الإشارات سلبية جداً فنياً ومالياً. البقاء مخاطرة."
    elif total_tech_score >= 3 and score_fund < 0:
        recommendation = "⚡ مضاربة بحذر"
        color = "#ffc107"
        strategy = "فني ممتاز للمضاربة السريعة، لكن احذر فالشركة ضعيفة مالياً."
    elif score_fund >= 4 and total_tech_score < 0:
        recommendation = "📉 صيد قيعان (Value Invest)"
        color = "#0d6efd"
        strategy = "السعر يهبط لكن الشركة قوية جداً. فرصة للمستثمر طويل النفس."

    # دمج الملاحظات
    tech_reasons = obs_dow + obs_vsa + obs_candle
    fund_reasons = obs_fund
    
    if not tech_reasons: tech_reasons.append("لا توجد إشارات فنية بارزة حالياً")
    if not fund_reasons: fund_reasons.append("البيانات المالية طبيعية، لا نقاط قوة أو ضعف حادة")

    return {
        "recommendation": recommendation,
        "color": color,
        "strategy": strategy,
        "tech_score": total_tech_score,
        "fund_score": score_fund,
        "tech_reasons": tech_reasons,
        "fund_reasons": fund_reasons,
        "trend": trend,
        "graham_price": metrics.get('Fair_Value_Graham')
    }
