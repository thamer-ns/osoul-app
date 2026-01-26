import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from market_data import get_chart_history
from config import DEFAULT_COLORS
import numpy as np

def render_technical_chart(symbol, period='1y', interval='1d'):
    if 'custom_colors' not in st.session_state: C = DEFAULT_COLORS
    else: C = st.session_state.custom_colors
    
    df = get_chart_history(symbol, period, interval)
    if df is None or df.empty: st.warning("لا توجد بيانات"); return

    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='MA20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='blue'), name='MA50'), row=1, col=1)
    colors = np.where(df['Close'] >= df['Open'], 'green', 'red')
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Vol'), row=2, col=1)
    
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, paper_bgcolor=C['card_bg'], plot_bgcolor=C['card_bg'], font=dict(family="Cairo", color=C['main_text']), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

def view_advanced_chart(fin):
    st.header("📈 التحليل الفني")
    trades = fin['all_trades']
    syms = list(trades['symbol'].unique()) if not trades.empty else []
    
    c1, c2 = st.columns([1, 3])
    with c1:
        st.markdown("**بحث:**"); manual = st.text_input("s_c", label_visibility="collapsed")
    with c2:
        st.markdown("**أو اختر:**"); sel = st.selectbox("s_l", syms, label_visibility="collapsed") if syms else None
    
    symbol = manual if manual else sel
    if symbol:
        st.markdown(f"### {symbol}")
        render_technical_chart(symbol)
