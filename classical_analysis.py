import streamlit as st
from market_data import get_chart_history

def render_classical_analysis(symbol):
    st.markdown("#### 🏛️ مستويات الدعم والمقاومة (Pivot Points)")
    
    # جلب بيانات 5 أيام
    df = get_chart_history(symbol, period="5d")
    
    if df is None or df.empty:
        st.warning("لا توجد بيانات كافية")
        return

    # أخذ آخر شمعة
    last = df.iloc[-1]
    H, L, C = last['High'], last['Low'], last['Close']
    
    # المعادلات
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)
    
    # العرض
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("مقاومة 2", f"{R2:.2f}")
    c2.metric("مقاومة 1", f"{R1:.2f}")
    c3.metric("الارتكاز", f"{PP:.2f}")
    c4.metric("دعم 1", f"{S1:.2f}")
    c5.metric("دعم 2", f"{S2:.2f}")
    
    # تحليل بسيط
    if C > PP:
        st.success(f"السعر ({C:.2f}) أعلى من الارتكاز (إيجابي)")
    else:
        st.error(f"السعر ({C:.2f}) أدنى من الارتكاز (سلبي)")
