import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from market_data import get_chart_history

# === الدالة الأولى: رسم الشارت (التي تحبها مع المؤشرات) ===
def render_technical_chart(symbol, period='1y', interval='1d'):
    """عرض الشارت الفني مع المؤشرات"""
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        C = DEFAULT_COLORS
    else: C = st.session_state.custom_colors

    df = get_chart_history(symbol, period, interval)
    if df is None or df.empty:
        st.warning("لا توجد بيانات فنية متاحة")
        return

    # الحسابات الفنية
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['STD20'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean().replace(0, 1)
    df['RSI'] = 100 - (100 / (1 + (gain/loss)))

    # MACD
    ema12 = df['Close'].ewm(span=12).mean()
    ema26 = df['Close'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    
    df.dropna(inplace=True)

    # الرسم
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=("السعر", "الحجم", "RSI", "MACD"))

    # السعر والبولنجر
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Up'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', name='BB Low'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary'], width=1.5), name='MA50'), row=1, col=1)

    # الحجم
    colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Vol'), row=2, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    # MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue'), name='MACD'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange'), name='Sig'), row=4, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACD']-df['Signal'], marker_color='gray', name='Hist'), row=4, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, paper_bgcolor=C['card_bg'], plot_bgcolor=C['card_bg'], font=dict(family="Cairo", color=C['main_text']), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# === الدالة الثانية: صفحة الاختيار (هذه كانت ناقصة وتسبب الخطأ) ===
def view_advanced_chart(fin):
    """واجهة لاختيار سهم ثم عرض الشارت"""
    st.header("📈 التحليل الفني")
    
    trades = fin['all_trades']
    symbols = []
    if not trades.empty:
        symbols = trades['symbol'].unique().tolist()
    
    # إضافة خيار يدوي
    col1, col2 = st.columns(2)
    with col1:
        manual_sym = st.text_input("بحث عن رمز (مثل 1120.SR)")
    with col2:
        selected_sym = st.selectbox("أو اختر من المحفظة", symbols) if symbols else None
    
    symbol = manual_sym if manual_sym else selected_sym
    
    if symbol:
        st.markdown(f"### {symbol}")
        # هنا نستدعي دالة الرسم الأساسية
        render_technical_chart(symbol)
    else:
        st.info("الرجاء اختيار سهم لعرض الشارت.")
