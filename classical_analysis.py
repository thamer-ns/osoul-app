import streamlit as st
import pandas as pd
import numpy as np
from market_data import get_chart_history

def calculate_fibonacci_levels(df):
    """حساب مستويات فيبوناتشي بناءً على آخر قمة وقاع رئيسيين"""
    # نأخذ بيانات 6 أشهر لتحديد القمة والقاع
    max_price = df['High'].max()
    min_price = df['Low'].min()
    diff = max_price - min_price
    
    levels = {
        'Top (100%)': max_price,
        'Golden (61.8%)': max_price - (0.618 * diff),
        'Half (50%)': max_price - (0.5 * diff),
        'Weak (38.2%)': max_price - (0.382 * diff),
        'Bottom (0%)': min_price
    }
    return levels, max_price, min_price

def render_classical_analysis(symbol):
    st.markdown("### 🏛️ التحليل الكلاسيكي (Price Action & Fibonacci)")
    
    df = get_chart_history(symbol, period="6mo", interval="1d")
    if df is None or len(df) < 20: 
        st.warning("بيانات غير كافية للتحليل الكلاسيكي")
        return

    curr_price = df['Close'].iloc[-1]
    
    # 1. حساب النقاط المحورية (Pivot Points - Standard)
    last_candle = df.iloc[-2] # شمعة أمس
    H, L, C = last_candle['High'], last_candle['Low'], last_candle['Close']
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)

    # 2. فيبوناتشي
    fibs, high_6m, low_6m = calculate_fibonacci_levels(df)

    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("مستويات فيبوناتشي (6 أشهر)")
        st.write(f"أعلى قمة: **{high_6m:.2f}** | أدنى قاع: **{low_6m:.2f}**")
        for name, price in fibs.items():
            color = "green" if price < curr_price else "red"
            st.markdown(f"- **{name}:** :{color}[{price:.2f}]")
            
    with c2:
        st.subheader("دعوم ومقاومات اليوم (Pivot)")
        st.metric("المقاومة الثانية (R2)", f"{R2:.2f}")
        st.metric("المقاومة الأولى (R1)", f"{R1:.2f}")
        st.metric("نقطة الارتكاز (PP)", f"{PP:.2f}", delta=round(curr_price - PP, 2))
        st.metric("الدعم الأول (S1)", f"{S1:.2f}")
        st.metric("الدعم الثاني (S2)", f"{S2:.2f}")

    # التفسير المنطقي
    st.markdown("---")
    st.markdown("#### 🧐 الخلاصة الكلاسيكية:")
    
    if curr_price > PP:
        st.success(f"السعر ({curr_price}) يتداول فوق نقطة الارتكاز ({PP:.2f})، مما يشير إلى سيطرة المشترين اليوم. الهدف القادم هو R1 عند {R1:.2f}.")
    else:
        st.error(f"السعر ({curr_price}) يتداول تحت نقطة الارتكاز ({PP:.2f})، السلبية تسيطر. الدعم القادم هو S1 عند {S1:.2f}.")

    # فيبوناتشي لوجيك
    if abs(curr_price - fibs['Golden (61.8%)']) / curr_price < 0.02:
        st.info("💡 **تنبيه:** السعر قريب جداً من النسبة الذهبية (61.8%). هذه المنطقة غالباً ما تكون منطقة ارتداد قوية.")
