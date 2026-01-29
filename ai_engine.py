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
    # فوليوم عالي جداً مع مدى (Spread) ضيق = تلاعب محتمل
    if current_vol > avg_vol * 1.5 and current_spread < avg_spread * 0.8:
        if curr['Close'] > prev['Close']: 
            # في قمة + فوليوم عالي + شمعة صغيرة = تصريف (Up-Thrust potential)
            score -= 2
            obs.append("VSA: جهد شرائي عالي بمدى ضيق (إشارة تصريف محتملة)")
        else: 
            # في قاع + فوليوم عالي + شمعة صغيرة = تجميع (Stopping Volume)
            score += 2
            obs.append("VSA: جهد بيعي عالي بمدى ضيق (إشارة تجميع/امتصاص)")

    # 2. اختبار العرض (Testing for Supply)
    # نزول للسعر ثم إغلاق مرتفع مع فوليوم منخفض = لا يوجد بائعين
    lower_wick = min(curr['Close'], curr['Open']) - curr['Low']
    body_size = abs(curr['Close'] - curr['Open'])
    
    if lower_wick > body_size * 2 and current_vol < avg_vol:
        score += 2
        obs.append("VSA: نجاح اختبار العرض (No Supply) - إشارة إيجابية")

    # 3. ذروة الشراء (Buying Climax)
    # فوليوم خيالي (3 أضعاف) مع ذيل علوي طويل
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
    # (تم تبسيطها برمجياً: السعر يصعد و RSI يهبط)
    rsi = _calculate_rsi(df)
    if df['Close'].iloc[-1] > df['Close'].iloc[-10] and rsi.iloc[-1] < rsi.iloc[-10]:
        score -= 1
        obs.append("انفراج سلبي (Bearish Divergence): السعر يصعد والعزم يهبط")

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
    
    # المطرقة (Hammer) - في القاع
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        score += 1
        patterns.append("شمعة المطرقة (Hammer) - انعكاسية إيجابية")
        
    # الابتلاع الشرائي (Bullish Engulfing)
    if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']: # خضراء بعد حمراء
        if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']: # جسم يبتلع جسم
            score += 2
            patterns.append("الابتلاع الشرائي (Bullish Engulfing) - إشارة دخول قوية")
            
    # الشهاب (Shooting Star) - في القمة
    if upper_wick > body * 2 and lower_wick < body * 0.5:
        score -= 1
        patterns.append("شمعة الشهاب (Shooting Star) - انعكاسية سلبية")

    return score, patterns

def _analyze_deep_financials(symbol):
    """
    التحليل المالي العميق
    المصدر: كتب القوائم المالية (تحليل جودة الأرباح والسيولة)
    """
    metrics = get_advanced_fundamental_ratios(symbol) # تستدعي دالتك من financial_analysis.py
    price = metrics.get('Current_Price', 0) # تأكد من تمرير السعر أو جلبه
    
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
    if fv and fv > 0 and price > 0:
        if price < fv * 0.7: # هامش أمان 30%
            score += 3
            obs.append(f"فرصة قيمة: السعر ({price}) أقل بكثير من القيمة العادلة ({fv:.2f})")
        elif price > fv * 1.4:
            score -= 2
            obs.append("السعر متضخم مقارنة بالقيمة العادلة")

    # 3. جودة الأرباح (Quality of Earnings)
    # هل الكاش التشغيلي يغطي صافي الربح؟
    # (هذه المعلومة تأتي من التحليل المالي في financial_analysis.py)
    # سنعتمد على التقييم النصي الموجود في metrics['Opinions']
    if "تدفق نقدي تشغيلي سالب" in metrics.get('Opinions', ''):
        score -= 2
        obs.append("جودة أرباح منخفضة (النقد التشغيلي سالب)")

    return score, obs, metrics

def _calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def generate_ai_report(symbol):
    """
    المعالج المركزي: يجمع التحليلات ويصدر التوصية
    """
    # جلب البيانات
    df = get_chart_history(symbol, period='2y')
    
    # تشغيل المحركات
    s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
    s_dow, o_dow, trend = _analyze_dow_theory_murphy(df)
    s_can, o_can = _detect_candlestick_patterns(df)
    s_fun, o_fun, m_fun = _analyze_deep_financials(symbol)
    
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
        strategy = "توافق ممتاز بين القوة المالية (جراهام) والإشارات الفنية (VSA + Dow). فرصة نادرة."
    elif total_score >= 4:
        recommendation = "✅ شراء / تجميع"
        color = "#28a745"
        strategy = "الاتجاه العام إيجابي والشركة مستقرة. مناسب للدخول."
    elif total_score <= -4:
        recommendation = "⛔ خروج / تجنب"
        color = "#dc3545" # Red
        strategy = "إشارات سلبية متعددة (تصريف فني أو ضعف مالي). الحفاظ على رأس المال أولى."
    elif tech_score >= 3 and fund_score < 0:
        recommendation = "⚡ مضاربة بحذر (Speculative)"
        color = "#ffc107" # Yellow
        strategy = "السهم جيد فنياً للمضاربة السريعة، لكن مالياً غير آمن للاستثمار الطويل."
    elif fund_score >= 4 and tech_score < 0:
        recommendation = "📉 استثمار قيمة (Value Invest)"
        color = "#0d6efd" # Blue
        strategy = "السعر يهبط لكن الشركة قوية جداً ورخيصة. فرصة للمستثمر الصبور (Buy the Dip)."

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
