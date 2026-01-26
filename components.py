import streamlit as st

def safe_fmt(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return "-"

def render_kpi(label, value, color="blue"):
    st.markdown(f"""
    <div class="kpi-card">
        <div style="color:#666; font-size:0.9rem;">{label}</div>
        <div style="color:#0052CC; font-size:1.5rem; font-weight:bold; direction:ltr;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    color = "green" if change >= 0 else "red"
    st.markdown(f"""
    <div style="background:white; padding:10px; border-radius:8px; border:1px solid #eee; margin-bottom:10px;">
        <div style="font-weight:bold;">{symbol}</div>
        <div style="font-size:1.2rem;">{price}</div>
        <div style="color:{color}; direction:ltr;">{change:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols):
    st.dataframe(df, use_container_width=True)
