import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from config import DEFAULT_COLORS

# دالة وهمية لجلب البيانات في حال عدم وجود market_data (للحماية من الأخطاء)
try:
    from market_data import get_chart_history
except ImportError:
    def get_chart_history(symbol, period='1y', interval='1d'):
        # إنشاء بيانات وهمية للتجربة إذا لم يوجد مصدر بيانات
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100)
        data = pd.DataFrame({
            'Open': np.random.rand(100) * 10 + 100,
            'High': np.random.rand(100) * 10 + 110,
            'Low': np.random.rand(100) * 10 + 90,
            'Close': np.random.rand(100) * 10 + 100,
            'Volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        return data

def view_advanced_chart(symbol, period='1y', interval='1d'):
    """عرض الشارت الفني مع المؤشرات - النسخة الأصلية"""
    
    # جلب الألوان
    if 'custom_colors' not in st.session_state:
        C = DEFAULT_COLORS
    else:
        C = st.session_state.custom_colors

    # جلب البيانات
    df = get_chart_history(symbol, period, interval)
    
    if df is None or df.empty:
        st.warning(f"لا توجد بيانات متاحة للسهم {symbol}")
        return

    # --- الحسابات الفنية (MA, BB, RSI, MACD) ---
    # 1. المتوسطات والبولنجر
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    
    # 2. RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().replace(0, 1)
    df['RSI'] = 100 - (100 / (1 + (gain/loss)))

    # 3. MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # تنظيف البيانات (حذف القيم الفارغة الناتجة عن الحسابات)
    df = df.iloc[50:]  # تجاوز أول 50 يوم لضمان دقة المتوسطات

    # --- الرسم البياني (Plotly) ---
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=[0.5, 0.1, 0.2, 0.2],
        subplot_titles=("حركة السعر", "الحجم", "مؤشر RSI", "مؤشر MACD")
    )

    # 1. الشموع والبولنجر
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Up', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', name='BB Low', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary'], width=1.5), name='MA 50'), row=1, col=1)

    # 2. الحجم (Volume)
    colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم', showlegend=False), row=2, col=1)

    # 3. RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1.5), name='RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    # 4. MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue', width=1.5), name='MACD'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange', width=1.5), name='Signal'), row=4, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACD']-df['Signal'], marker_color='gray', name='Hist'), row=4, col=1)

    # تنسيق المظهر العام
    fig.update_layout(
        height=900, 
        xaxis_rangeslider_visible=False, 
        paper_bgcolor=C['card_bg'], 
        plot_bgcolor=C['card_bg'], 
        font=dict(family="Cairo, sans-serif", color=C['main_text']),
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode='x unified'
    )
    
    # إزالة الخطوط الشبكية الزائدة
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=C['border'], zeroline=False)

    st.plotly_chart(fig, use_container_width=True)
