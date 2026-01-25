import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from market_data import get_chart_history

def render_technical_chart(symbol, period='1y', interval='1d'):
    """عرض الشارت الفني مع المؤشرات (MACD, RSI, Bollinger)"""
    
    # جلب الألوان من الكونفيج
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        C = DEFAULT_COLORS
    else: C = st.session_state.custom_colors

    # جلب البيانات
    df = get_chart_history(symbol, period, interval)
    if df is None or df.empty:
        st.warning("لا توجد بيانات فنية متاحة لهذا السهم")
        return

    # --- الحسابات الفنية ---
    # 1. المتوسطات والبولنجر
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['STD20'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    
    # 2. RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean().replace(0, 1)
    df['RSI'] = 100 - (100 / (1 + (gain/loss)))

    # 3. MACD
    ema12 = df['Close'].ewm(span=12).mean()
    ema26 = df['Close'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    
    # تنظيف البيانات الناقصة الناتجة عن الحسابات
    df.dropna(inplace=True)

    # --- الرسم البياني ---
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=("حركة السعر", "أحجام التداول", "مؤشر RSI", "مؤشر MACD")
    )

    # 1. السعر والبولنجر (الصف الأول)
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='الشموع'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB علوي'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', name='BB سفلي'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary'], width=1.5), name='متوسط 50'), row=1, col=1)

    # 2. الحجم (الصف الثاني)
    colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)

    # 3. مؤشر RSI (الصف الثالث)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    # 4. مؤشر MACD (الصف الرابع)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue'), name='MACD'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange'), name='إشارة'), row=4, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACD']-df['Signal'], marker_color='gray', name='الهستوجرام'), row=4, col=1)

    # تنسيق الشكل العام
    fig.update_layout(
        height=900, 
        xaxis_rangeslider_visible=False, 
        paper_bgcolor=C['card_bg'], 
        plot_bgcolor=C['card_bg'], 
        font=dict(family="Cairo", color=C['main_text']), 
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10)
    )
    
    # إصلاح الشبكة (Grid)
    fig.update_xaxes(showgrid=True, gridcolor=C['border'])
    fig.update_yaxes(showgrid=True, gridcolor=C['border'])

    st.plotly_chart(fig, use_container_width=True)

# === هذا السطر هو الحل لمشكلة الخطأ ===
# نقوم بتعريف الاسم الذي يبحث عنه views.py ونربطه بالدالة الموجودة
view_advanced_chart = render_technical_chart
