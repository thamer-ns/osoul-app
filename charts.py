import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from market_data import get_chart_history
from config import DEFAULT_COLORS
import numpy as np

def view_advanced_chart(symbol):
    if not symbol: return
    
    # جلب البيانات
    df = get_chart_history(symbol, period="1y")
    
    if df is None or df.empty:
        st.warning(f"لا توجد بيانات للسهم {symbol}")
        return

    # إعداد الألوان
    if 'custom_colors' in st.session_state:
        C = st.session_state.custom_colors
    else:
        C = DEFAULT_COLORS

    # التحليل البسيط (المتوسطات)
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()

    # الرسم
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f'تحرك السعر: {symbol}', 'حجم التداول'), 
                        row_heights=[0.7, 0.3])

    # الشموع
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                    low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)

    # المتوسطات
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='MA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='blue', width=1), name='MA 50'), row=1, col=1)

    # الحجم (Volume)
    colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)

    # التنسيق
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=600,
        paper_bgcolor=C['card_bg'],
        plot_bgcolor=C['card_bg'],
        font=dict(family="Cairo", color=C['main_text']),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1, x=0, xanchor="left", yanchor="bottom")
    )
    
    st.plotly_chart(fig, use_container_width=True)
