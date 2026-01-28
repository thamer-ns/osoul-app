import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from market_data import get_chart_history

def render_technical_chart(symbol, period='2y', interval='1d'):
    df = get_chart_history(symbol, period, interval)
    if df is None or len(df) < 50: 
        st.warning("البيانات التاريخية غير كافية للتحليل الفني الدقيق.")
        return

    # 1. المؤشرات الفنية (Technical Indicators)
    # SMA 50 & 200 (لتحديد الاتجاه العام والتقاطعات الذهبية)
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    # Bollinger Bands (لقياس التذبذب)
    df['STD_20'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df.rolling(20)['Close'].mean() + (df['STD_20'] * 2)
    df['BB_Lower'] = df.rolling(20)['Close'].mean() - (df['STD_20'] * 2)
    
    # RSI (الزخم)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 2. المنطق التحليلي (Interpreted Logic)
    last_close = df['Close'].iloc[-1]
    last_sma50 = df['SMA_50'].iloc[-1]
    last_sma200 = df['SMA_200'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]
    
    trend_status = "صاعد 🐂" if last_close > last_sma200 else "هابط 🐻"
    cross_status = "تقاطع ذهبي ✨" if last_sma50 > last_sma200 else "تقاطع موت 💀"
    
    # الرسم البياني
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2],
                        subplot_titles=(f"السعر ({trend_status})", "الزخم (RSI)", "MACD"))

    # الشموع
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
    
    # المتوسطات
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], line=dict(color='orange', width=1.5), name='SMA 50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], line=dict(color='blue', width=2), name='SMA 200 (Trend)'), row=1, col=1)
    
    # بولنجر
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(200,200,200,0.1)', showlegend=False), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD
    fig.add_trace(go.Bar(x=df.index, y=df['MACD']-df['Signal_Line'], name='Hist'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], name='Signal'), row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    # 3. التحليل النصي (جون ميرفي ستايل)
    st.markdown("#### 🔭 رؤية فنية (جون ميرفي):")
    cols = st.columns(3)
    
    # تحليل المتوسطات
    with cols[0]:
        st.write("**الاتجاه العام:**")
        if last_close > last_sma200:
            st.success("إيجابي: السعر يتداول فوق متوسط 200 يوم.")
        else:
            st.error("سلبي: السعر تحت متوسط 200 يوم (سوق دببة).")
            
        if last_sma50 > last_sma200:
            st.info("الترتيب إيجابي (50 > 200).")
            
    # تحليل الزخم
    with cols[1]:
        st.write("**الزخم (RSI):**")
        if last_rsi > 70:
            st.warning("تشبع شرائي: احذر من التصحيح.")
        elif last_rsi < 30:
            st.success("تشبع بيعي: فرصة ارتداد محتملة.")
        else:
            st.write("منطقة حيادية (تداول طبيعي).")
            
    # تحليل التذبذب
    with cols[2]:
        st.write("**التذبذب (Bollinger):**")
        bb_width = (df['BB_Upper'].iloc[-1] - df['BB_Lower'].iloc[-1]) / df['SMA_200'].iloc[-1]
        if bb_width < 0.10: # رقم تقريبي
            st.info("انحسار سعري (Squeeze): توقع حركة قوية قادمة.")
        else:
            st.write("تذبذب طبيعي.")
