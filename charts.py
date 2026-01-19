import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from market_data import get_chart_history

def calculate_technical_indicators(df):
    if df is None or df.empty: return df
    
    # RSI Calculation
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    loss = loss.replace(0, 1) # تجنب القسمة على صفر
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Moving Averages
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    
    # Bollinger Bands
    df['BB_Upper'] = df['MA20'] + (df['Close'].rolling(20).std() * 2)
    df['BB_Lower'] = df['MA20'] - (df['Close'].rolling(20).std() * 2)
    
    # MACD Calculation
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # حذف القيم الفارغة الناتجة عن المتوسطات (أول 50 شمعة) لتنظيف الرسم
    df.dropna(inplace=True)
    
    return df

def render_technical_chart(symbol, period, interval):
    # جلب الألوان من الإعدادات أو استخدام الافتراضي
    if 'custom_colors' not in st.session_state:
        try:
            from config import DEFAULT_COLORS
            C = DEFAULT_COLORS
        except ImportError:
            # ألوان احتياطية في حال فشل الاستيراد
            C = {'primary': '#0e6ba8', 'success': '#10B981', 'danger': '#EF4444', 
                 'card_bg': '#FFFFFF', 'main_text': '#1F2937'}
    else:
        C = st.session_state.custom_colors

    with st.spinner("جاري تحميل البيانات الفنية..."):
        df = get_chart_history(symbol, period, interval)
    
    if df is None or df.empty:
        st.warning("لا توجد بيانات متاحة لهذا السهم")
        return

    df = calculate_technical_indicators(df)

    if df.empty:
        st.warning("البيانات غير كافية لحساب المؤشرات الفنية")
        return

    # إعداد الـ Subplots
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=("حركة السعر والبولنجر", "أحجام التداول", "RSI", "MACD")
    )

    # 1. السعر والبولنجر (الصف الأول)
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Upper'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', name='BB Lower'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary'], width=1.5), name='MA 50'), row=1, col=1)

    # 2. أحجام التداول (الصف الثاني)
    colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)

    # 3. مؤشر RSI (الصف الثالث)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#A855F7', width=1.5), name='RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    # 4. مؤشر MACD (الصف الرابع) - هنا كان الخطأ وتم تصحيحه
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#2563EB', width=1.5), name='MACD'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], line=dict(color='#F59E0B', width=1.5), name='Signal'), row=4, col=1)
    
    # استخدام go.Bar داخل add_trace بدلاً من add_bar المباشرة
    fig.add_trace(go.Bar(x=df.index, y=(df['MACD'] - df['Signal_Line']), name='Hist', marker_color='gray'), row=4, col=1)

    # تحسين التنسيق العام
    fig.update_layout(
        height=900, 
        xaxis_rangeslider_visible=False, 
        paper_bgcolor=C['card_bg'], 
        plot_bgcolor=C['card_bg'], 
        font=dict(family="Cairo", color=C['main_text']), 
        margin=dict(l=10, r=10, t=30, b=10), 
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)
