import pandas as pd
import numpy as np
from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ==========================================
# 🧠 المحرك الاستشاري الذكي (Expert System)
# ==========================================

def _analyze_technicals(df):
    """تحليل فني بناءً على منهجية جون ميرفي"""
    if df is None or len(df) < 200: return 0, "بيانات غير كافية", "محايد"
    
    score = 0
    reasons = []
    
    # 1. الاتجاه (Trend) - وزن عالي
    curr = df['Close'].iloc[-1]
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    sma200 = df['Close'].rolling(200).mean().iloc[-1]
    
    if curr > sma200:
        score += 2
        reasons.append("السعر فوق متوسط 200 يوم (اتجاه صاعد)")
    else:
        score -= 2
        reasons.append("السعر تحت متوسط 200 يوم (اتجاه هابط)")
        
    if sma50 > sma200:
        score += 1
        reasons.append("الترتيب إيجابي للمتوسطات (Golden Cross محتمل)")
        
    # 2. الزخم (Momentum - RSI)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = rsi.iloc[-1]
    
    if last_rsi < 30:
        score += 2
        reasons.append("RSI في مناطق تشبع بيعي (فرصة ارتداد)")
    elif last_rsi > 70:
        score -= 1
        reasons.append("RSI في مناطق تشبع شرائي (تضخم)")
        
    # 3. السيولة (Volume)
    vol_sma = df['Volume'].rolling(20).mean().iloc[-1]
    curr_vol = df['Volume'].iloc[-1]
    if curr_vol > vol_sma * 1.5:
        score += 1
        reasons.append("سيولة عالية اليوم تدعم الحركة الحالية")
        
    trend_desc = "صاعد بقوة" if score >= 3 else "إيجابي" if score > 0 else "سلبي"
    return score, reasons, trend_desc

def _analyze_fundamentals(symbol):
    """تحليل مالي (جراهام + بيوتروسكي)"""
    metrics, price = get_advanced_fundamental_ratios(symbol)
    score = 0
    reasons = []
    
    # 1. المتانة المالية (Piotroski)
    f_score = metrics.get('Piotroski_Score', 0)
    if f_score >= 7:
        score += 3
        reasons.append(f"مركز مالي قوي جداً (F-Score {f_score}/9)")
    elif f_score >= 5:
        score += 1
        reasons.append("مركز مالي مستقر")
    else:
        score -= 2
        reasons.append("ضعف في الكفاءة التشغيلية أو الديون")
        
    # 2. القيمة العادلة (Graham)
    fv = metrics.get('Fair_Value_Graham')
    if fv and fv > 0:
        if price < fv * 0.8: # خصم 20%
            score += 3
            reasons.append(f"يتداول بخصم مغري عن القيمة العادلة ({fv:.2f})")
        elif price < fv:
            score += 1
            reasons.append("أقل من القيمة العادلة")
        elif price > fv * 1.3:
            score -= 2
            reasons.append("السعر متضخم مقارنة بالقيمة العادلة")
            
    return score, reasons, metrics

def generate_ai_report(symbol):
    """توليد التقرير النهائي المدمج"""
    df = get_chart_history(symbol, period='2y')
    
    # 1. تنفيذ التحليلات
    t_score, t_reasons, t_trend = _analyze_technicals(df)
    f_score, f_reasons, f_metrics = _analyze_fundamentals(symbol)
    
    total_score = t_score + f_score
    
    # 2. صناعة القرار (Decision Matrix)
    recommendation = ""
    color = "gray"
    
    if total_score >= 5:
        recommendation = "💎 فرصة ذهبية (شراء قوي)"
        color = "green"
        strategy = "هذا السهم يجمع بين القوة الفنية والمالية. مناسب للاستثمار والنمو."
    elif t_score >= 2 and f_score < 0:
        recommendation = "⚡ مضاربة بحذر"
        color = "orange"
        strategy = "السهم جيد فنياً للمضاربة، لكن وضعه المالي ضعيف. التزم بوقف الخسارة."
    elif f_score >= 3 and t_score < 0:
        recommendation = "🏗️ تجميع استثماري (Value Buy)"
        color = "blue"
        strategy = "السهم ممتاز مالياً ورخيص، لكنه في اتجاه هابط فنياً. مناسب للمستثمر الصبور (تجميع على دفعات)."
    elif total_score <= -3:
        recommendation = "⛔ تجنب / خروج"
        color = "red"
        strategy = "السلبية تسيطر فنياً ومالياً. البحث عن فرص بديلة أفضل."
    else:
        recommendation = "⚖️ احتفاظ / مراقبة"
        color = "gray"
        strategy = "الأدلة متضاربة. يفضل الانتظار حتى تتضح الرؤية."

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
