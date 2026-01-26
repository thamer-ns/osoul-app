import streamlit as st
from market_data import get_chart_history

def render_classical_analysis(symbol):
    st.markdown("#### 🏛️ مستويات الدعم والمقاومة (Pivot Points)")
    df = get_chart_history(symbol, period="5d")
    
    if df is None or df.empty:
        st.warning("لا توجد بيانات كافية")
        return

    last = df.iloc[-1]
    H, L, C = last['High'], last['Low'], last['Close']
    
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)
    
    c1, c2, c3 = st.columns(3)
    c1.success(f"المقاومة 1: {R1:.2f}")
    c2.info(f"الارتكاز: {PP:.2f}")
    c3.error(f"الدعم 1: {S1:.2f}")
