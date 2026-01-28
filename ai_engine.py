import pandas as pd
import numpy as np
from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ==========================================
# 🧠 المحرك الاستشاري الذكي (Expert System V2)
# ==========================================

def _detect_candlestick_patterns(df):
    """
    اكتشاف نماذج الشموع اليابانية بناءً على الكتب المرفقة
    (المطرقة، دوجي، الابتلاع، الشهاب)
    """
    if df is None or len(df) < 3: return 0, []
    
    score = 0
    patterns = []
    
    # بيانات آخر شمعة
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # حساب جسم الشمعة والذيول
    body = abs(curr['Close'] - curr['Open'])
    upper_shadow = curr['High'] - max(curr['Close'], curr['Open'])
    lower_shadow = min(curr['Close'], curr['Open']) - curr['Low']
    total_range = curr['High'] - curr['Low']
    avg_body = abs(df['Close'] - df['Open']).rolling(10).mean().iloc[-1]
    
    # 1. المطرقة (Hammer) - إشارة إيجابية في القاع
    # شرط: ذيل سفلي طويل (ضعف الجسم)، جسم صغير، ذيل علوي صغير
    is_hammer = (lower_shadow > body * 2) and (upper_shadow < body * 0.5)
    
    # 2. الشهاب (Shooting Star) - إشارة سلبية في القمة
    is_shooting_star = (upper_shadow > body * 2) and (lower_shadow < body * 0.5)
    
    # 3. دوجي (Doji) - حيرة وانعكاس محتمل
    is_doji = body <= (total_range * 0.1)
    
    # 4. الابتلاع الشرائي (Bullish Engulfing) - إيجابي قوي
    # شرط: الشمعة الحالية خضراء وتبتلع جسم الشمعة الحمراء السابقة
    is_bull_engulfing = (curr['Close'] > curr['Open']) and \
                        (prev['Close'] < prev['Open']) and \
                        (curr['Close'] > prev['Open']) and \
                        (curr['Open'] < prev['Close'])

    # 5. الابتلاع البيعي (Bearish Engulfing) - سلبي قوي
    is_bear_engulfing = (curr['Close'] < curr['Open']) and \
                        (prev['Close'] > prev['Open']) and \
                        (curr['Close'] < prev['Close']) and \
                        (curr['Open'] > prev['Open'])

    # تسجيل النتائج
    if is_bull_engulfing:
        score += 2
        patterns.append("نموذج ابتلاع شرائي (Bullish Engulfing) - إشارة قوية للصعود")
    elif is_hammer:
        score += 1
        patterns.append("شمعة المطرقة (Hammer) - احتمال انعكاس إيجابي")
        
    if is_bear_engulfing:
        score -= 2
        patterns.append("نموذج ابتلاع بيعي (Bearish Engulfing) - إشارة سلبية")
    elif is_shooting_star:
        score -= 1
        patterns.append("شمعة الشهاب (Shooting Star) - احتمال هبوط")
        
    if is_doji:
        patterns.append("شمعة دوجي (Doji) - حيرة في السوق (ترقب)")

    return score, patterns

def _analyze_technicals(df):
    """تحليل فني (مؤشرات + شموع)"""
    if df is None or len(df) < 200: return 0, ["بيانات غير كافية"], "محايد"
    
    score = 0
    reasons = []
    
    # --- أ. المؤشرات الكلاسيكية (جون ميرفي) ---
    curr = df['Close'].iloc[-1]
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    sma200 = df['Close'].rolling(200).mean().iloc[-1]
    
    # الاتجاه
    if curr > sma200:
        score += 2
        reasons.append("السعر فوق متوسط 200 يوم (مسار صاعد)")
    else:
        score -= 2
        reasons.append("السعر تحت متوسط 200 يوم (مسار هابط)")
        
    # التقاطعات
    if sma50 > sma200:
        score += 1
    elif sma50 < sma200:
        score -= 1
        
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = rsi.iloc[-1]
    
    if last_rsi < 30:
        score += 2
        reasons.append("RSI: تشبع بيعي (مناطق ارتداد)")
    elif last_rsi > 70:
        score -= 1
        reasons.append("RSI: تشبع شرائي (تضخم)")

    # --- ب. الشموع اليابانية (الإضافة الجديدة) ---
    candle_score, candle_patterns = _detect_candlestick_patterns(df)
    score += candle_score
    reasons.extend(candle_patterns)
    
    trend_desc = "إيجابي" if score > 0 else "سلبي"
    return score, reasons, trend_desc

def _analyze_fundamentals(symbol):
    """تحليل مالي (جراهام + بيوتروسكي)"""
    metrics, price = get_advanced_fundamental_ratios(symbol)
    score = 0
    reasons = []
    
    # F-Score
    f_score = metrics.get('Piotroski_Score', 0)
    if f_score >= 7:
        score += 3
        reasons.append(f"مالية قوية (F-Score {f_score}/9)")
    elif f_score <= 3:
        score -= 2
        reasons.append("ضعف مالي أو ديون مرتفعة")
        
    # Graham Value
    fv = metrics.get('Fair_Value_Graham')
    if fv and fv > 0:
        if price < fv:
            score += 2
            reasons.append(f"سعر مغري (أقل من القيمة العادلة {fv:.2f})")
        elif price > fv * 1.5:
            score -= 2
            reasons.append("سعر متضخم جداً")
            
    return score, reasons, metrics

def generate_ai_report(symbol):
    """توليد التقرير النهائي"""
    df = get_chart_history(symbol, period='2y')
    
    t_score, t_reasons, t_trend = _analyze_technicals(df)
    f_score, f_reasons, f_metrics = _analyze_fundamentals(symbol)
    
    total_score = t_score + f_score
    
    # مصفوفة اتخاذ القرار
    recommendation = "احتفاظ / مراقبة"
    color = "#6c757d" # رمادي
    strategy = "تضارب في الإشارات. يفضل الانتظار."
    
    if total_score >= 6:
        recommendation = "💎 فرصة ذهبية (Strong Buy)"
        color = "#198754" # أخضر غامق
        strategy = "توافق فني ومالي ممتاز. الشموع والمؤشرات تدعم الصعود، والشركة قوية مالياً."
    elif total_score >= 3:
        recommendation = "✅ شراء / زيادة مراكز"
        color = "#28a745" # أخضر
        strategy = "الإيجابية تغلب على السهم. جيد للتمركز الاستثماري."
    elif total_score <= -4:
        recommendation = "⛔ خروج / تجنب"
        color = "#dc3545" # أحمر
        strategy = "إشارات سلبية قوية (مالية وفنية). خطر الهبوط مرتفع."
    elif t_score > 2 and f_score < 0:
        recommendation = "⚡ مضاربة لحظية فقط"
        color = "#ffc107" # أصفر
        strategy = "فنيا جيد لكن مالياً ضعيف. ضارب مع وقف خسارة صارم ولا تستثمر."
    elif f_score > 3 and t_score < 0:
        recommendation = "📉 تجميع استثماري (القيمة)"
        color = "#0d6efd" # أزرق
        strategy = "السعر يهبط لكن الشركة قوية جداً. فرصة للمستثمر طويل الأمد (Buy the Dip)."

    return {
        "recommendation": recommendation,
        "color": color,
        "strategy": strategy,
        "tech_score": t_score,
        "fund_score": f_score,
        "tech_reasons": t_reasons,
        "fund_reasons": f_reasons,
        "trend": t_trend
    }
