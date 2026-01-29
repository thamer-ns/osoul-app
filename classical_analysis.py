import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from market_data import get_chart_history

def calculate_fibonacci_levels(df):
    """
    حساب مستويات فيبوناتشي وتحديد ما إذا كان السعر يرتد أم يخترق
    """
    max_price = df['High'].max()
    min_price = df['Low'].min()
    diff = max_price - min_price
    
    # مستويات فيبوناتشي (التصحيحية)
    # نفترض الرسم من القاع للقمة (لقياس الدعم في حال التصحيح)
    levels = {
        'Top (100%)': max_price,
        'Golden (61.8%)': max_price - (0.382 * diff), # ملاحظة: 61.8% تصحيح يعني نزولنا 38.2% من القمة أو العكس حسب طريقة الرسم، هنا اعتمدت القياس من القاع
        'Mid (50%)': max_price - (0.5 * diff),
        'Weak (38.2%)': max_price - (0.618 * diff),
        'Bottom (0%)': min_price
    }
    return levels

def render_classical_analysis(symbol):
    st.markdown("### 🏛️ التحليل الكلاسيكي (Price Action & Pivot Points)")
    
    # جلب بيانات 6 أشهر لتوضيح الصورة الكبيرة
    df = get_chart_history(symbol, period="6mo", interval="1d")
    if df is None or len(df) < 20: 
        st.warning("بيانات غير كافية للتحليل الكلاسيكي")
        return

    curr_price = df['Close'].iloc[-1]
    
    # 1. حساب النقاط المحورية (Pivot Points - Standard) لليوم الحالي
    last_candle = df.iloc[-2] # شمعة أمس المكتملة
    H, L, C = last_candle['High'], last_candle['Low'], last_candle['Close']
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)

    # 2. مستويات فيبوناتشي
    fibs = calculate_fibonacci_levels(df)

    # --- العرض المرئي (Chart) ---
    fig = go.Figure()

    # رسم الشموع (آخر 3 شهور فقط للوضوح)
    plot_df = df.tail(90)
    fig.add_trace(go.Candlestick(
        x=plot_df.index, open=plot_df['Open'], high=plot_df['High'],
        low=plot_df['Low'], close=plot_df['Close'], name='السعر'
    ))

    # إضافة خطوط فيبوناتشي (تمتد على كامل الشارت)
    for name, level in fibs.items():
        color = 'gold' if 'Golden' in name else ('gray' if 'Top' in name or 'Bottom' in name else 'blue')
        width = 2 if 'Golden' in name else 1
        dash = 'solid' if 'Golden' in name else 'dot'
        
        fig.add_hline(y=level, line_dash=dash, line_color=color, line_width=width, 
                      annotation_text=f"{name}: {level:.2f}", annotation_position="top left")

    # إضافة خطوط البايفوت (Pivot Points) - نظهرها كخطوط قصيرة في آخر الشارت
    # نستخدم Scatter لرسم خطوط أفقية قصيرة لليوم الحالي فقط
    last_date = plot_df.index[-1]
    # خدعة لتمديد الخط قليلاً لليمين (نحتاج تعديل x axis لو أردنا، لكن هنا سنرسم خطوط عادية ملونة)
    
    pivot_levels = [
        (R2, "R2", "red"), (R1, "R1", "red"),
        (PP, "Pivot", "black"),
        (S1, "S1", "green"), (S2, "S2", "green")
    ]
    
    for level, name, color in pivot_levels:
        fig.add_hline(y=level, line_dash="dashdot", line_color=color, line_width=1,
                      annotation_text=f"daily {name}", annotation_position="bottom right")

    fig.update_layout(
        title=f"خريطة الأسعار والمستويات الرئيسية لـ {symbol}",
        height=500,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- لوحة المعلومات (Dashboard) ---
    st.markdown("#### 🔢 الأرقام الرئيسية لليوم:")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("المقاومة 2", f"{R2:.2f}", delta_color="inverse")
    col2.metric("المقاومة 1", f"{R1:.2f}", delta_color="inverse")
    col3.metric("الارتكاز (PP)", f"{PP:.2f}", delta=round(curr_price - PP, 2))
    col4.metric("الدعم 1", f"{S1:.2f}")
    col5.metric("الدعم 2", f"{S2:.2f}")

    # --- الخلاصة الذكية ---
    st.markdown("---")
    
    # تحليل البايفوت
    if curr_price > PP:
        pivot_msg = "✅ **إيجابي:** السعر يتداول فوق نقطة الارتكاز اليومية. يفضل البحث عن فرص الشراء باستهداف R1."
        pivot_type = "success"
    else:
        pivot_msg = "🔻 **سلبي:** السعر يتداول تحت نقطة الارتكاز اليومية. البائعون هم المسيطرون، الدعم القادم هو S1."
        pivot_type = "error"
        
    # تحليل فيبوناتشي (القرب من المستويات)
    fib_msg = ""
    closest_fib = min(fibs.items(), key=lambda x: abs(x[1] - curr_price))
    distance_pct = abs(curr_price - closest_fib[1]) / curr_price * 100
    
    if distance_pct < 1.5: # إذا كان الفرق أقل من 1.5%
        fib_msg = f"💡 **تنبيه:** السعر يتداول بالقرب جداً من مستوى فيبوناتشي ({closest_fib[0]}). راقب حركة السعر هنا (ارتداد أو كسر)."
    
    # عرض الرسائل
    if pivot_type == "success":
        st.success(pivot_msg)
    else:
        st.error(pivot_msg)
        
    if fib_msg:
        st.info(fib_msg)
