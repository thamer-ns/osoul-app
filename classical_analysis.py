import streamlit as st
import pandas as pd
from market_data import get_chart_history

def render_classical_analysis(symbol):
    """التحليل الكلاسيكي (نقاط الارتكاز والدعوم والمقاومات)"""
    st.markdown("#### 🏛️ مستويات الدعم والمقاومة (Pivot Points)")
    
    # جلب بيانات آخر يوم
    df = get_chart_history(symbol, period="5d", interval="1d")
    if df is None or df.empty:
        st.warning("لا توجد بيانات كافية للحساب")
        return

    last_day = df.iloc[-1]
    H = last_day['High']
    L = last_day['Low']
    C = last_day['Close']
    
    # حساب البيفوت الكلاسيكي
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)
    R3 = H + 2 * (PP - L)
    S3 = L - 2 * (H - PP)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"**المقاومات (للبيع):**")
        st.success(f"R3: {R3:.2f}")
        st.success(f"R2: {R2:.2f}")
        st.success(f"R1: {R1:.2f}")
        
    with col2:
        st.markdown(f"**نقطة الارتكاز:**")
        st.info(f"PP: {PP:.2f}")
        st.markdown(f"*السعر الحالي: {C:.2f}*")
        
    with col3:
        st.markdown(f"**الدعوم (للشراء):**")
        st.error(f"S1: {S1:.2f}")
        st.error(f"S2: {S2:.2f}")
        st.error(f"S3: {S3:.2f}")

    st.markdown("---")
    st.caption("💡 الاستراتيجية الكلاسيكية: إذا كان السعر فوق الارتكاز فالإتجاه إيجابي، وإذا تحته فالإتجاه سلبي. استخدم الدعوم كنقاط شراء والمقاومات كأهداف بيع.")
