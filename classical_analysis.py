import streamlit as st
import pandas as pd
from market_data import get_chart_history

def render_classical_analysis(symbol):
    st.markdown("#### 🏛️ دعوم ومقاومات (Pivot Points)")
    df = get_chart_history(symbol, period="5d", interval="1d")
    if df is None or len(df) < 2: st.warning("بيانات غير كافية"); return

    # نأخذ شمعة أمس لحساب مستويات اليوم
    prev = df.iloc[-2]; curr = df.iloc[-1]['Close']
    H, L, C = prev['High'], prev['Low'], prev['Close']
    
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L; S1 = (2 * PP) - H
    R2 = PP + (H - L); S2 = PP - (H - L)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("مقاومة 1", f"{R1:.2f}"); c2.metric("الارتكاز", f"{PP:.2f}"); c3.metric("دعم 1", f"{S1:.2f}")
    
    if curr > PP: st.success(f"إيجابي: السعر ({curr:.2f}) أعلى من الارتكاز")
    else: st.error(f"سلبي: السعر ({curr:.2f}) أدنى من الارتكاز")
