import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from market_data import get_chart_history

def render_technical_chart(symbol, period='2y', interval='1d'):
    # جلب البيانات
    df = get_chart_history(symbol, period, interval)
    if df is None or len(df) < 200: 
        st.warning(f"البيانات التاريخية غير كافية ({len(df) if df is not None else 0} شمعة). نحتاج 200 على الأقل.")
        return

    # --- 1. الحسابات الفنية ---
    
    # المتوسطات المتحركة
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    # Bollinger Bands
    df['STD_20'] = df['Close'].rolling(20).std()
    df['BB_Middle'] = df['Close'].rolling(20).mean()
    df['BB_Upper'] = df['BB_Middle'] + (df['STD_20'] * 2)
    df['BB_Lower'] = df['BB_Middle'] - (df['STD_20'] * 2)
    
    # Squeeze Logic (مطور): حساب عرض النطاق كنسبة مئوية
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
    # نعتبره Squeeze إذا كان العرض الحالي أقل من أدنى عرض في آخر 6 أشهر (تقريباً 126 يوم تداول)
    min_width_6m = df['BB_Width'].rolling(window=126).min()
    is_squeeze = df['BB_Width'].iloc[-1] <= (min_width_6m.iloc[-1] * 1.05) # سماحية 5%

    # RSI (محسّن)
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
    df['MACD_Hist'] = df['MACD'] - df['Signal_Line']

    # تنظيف البيانات (حذف القيم الفارغة الناتجة عن المتوسطات لضمان رسم نظيف)
    plot_df = df.iloc[200:].copy() # نبدأ الرسم بعد اكتمال متوسط 200
    
    # القيم الحالية للتحليل
    last_close = df['Close'].iloc[-1]
    last_sma50 = df['SMA_50'].iloc[-1]
    last_sma200 = df['SMA_200'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]

    # --- 2. الرسم البياني ---
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(f"تحليل السعر: {symbol}", "RSI (الزخم)", "MACD")
    )

    # الشموع اليابانية
    fig.add_trace(go.Candlestick(
        x=plot_df.index, open=plot_df['Open'], high=plot_df['High'],
        low=plot_df['Low'], close=plot_df['Close'], name='السعر',
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)
    
    # المتوسطات
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SMA_50'], line=dict(color='orange', width=1.5), name='SMA 50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SMA_200'], line=dict(color='#2962FF', width=2), name='SMA 200'), row=1, col=1)
    
    # البولنجر (تظليل الخلفية)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(0,0,255,0.05)', showlegend=False), row=1, col=1)

    # RSI Plot
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], line=dict(color='purple', width=2), name='RSI'), row=2, col=1)
    fig.add_hrect(y0=30, y1=70, row=2, col=1, fillcolor="gray", opacity=0.1, line_width=0)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD Plot
    # تلوين الهستوجرام (أخضر للإيجابي وأحمر للسلبي)
    colors = np.where(plot_df['MACD_Hist'] >= 0, '#26a69a', '#ef5350')
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], marker_color=colors, name='Hist'), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], line=dict(color='#2962FF'), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Signal_Line'], line=dict(color='#FF6D00'), name='Signal'), row=3, col=1)

    # تحسينات التنسيق العامة
    fig.update_layout(
        height=800, 
        xaxis_rangeslider_visible=False, 
        showlegend=True,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode='x unified' # ميزة رائعة لإظهار كل القيم عند تمرير الماوس
    )
    
    # إخفاء عناوين المحور السيني للمخططات العلوية
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

    # --- 3. التحليل النصي (المنطق المفسر) ---
    st.markdown("#### 🔭 الرؤية الفنية (John Murphy Style):")
    
    # إنشاء بطاقات (Metric Cards) بدلاً من نص عادي
    c1, c2, c3 = st.columns(3)
    
    with c1:
        trend_label = "صاعد (Bullish)" if last_close > last_sma200 else "هابط (Bearish)"
        trend_color = "normal" if last_close > last_sma200 else "inverse"
        st.metric("الاتجاه العام (SMA 200)", trend_label, delta_color=trend_color)
        
        if last_sma50 > last_sma200:
            st.caption("✅ المتوسطات في ترتيب إيجابي.")
        else:
            st.caption("⚠️ المتوسطات في ترتيب سلبي.")

    with c2:
        rsi_status = "محايد"
        if last_rsi > 70: rsi_status = "تشبع شرائي (خطر)"
        elif last_rsi < 30: rsi_status = "تشبع بيعي (فرصة)"
        
        st.metric("الزخم (RSI 14)", f"{last_rsi:.1f}", rsi_status)

    with c3:
        volatility_status = "طبيعي"
        if is_squeeze:
            volatility_status = "🔥 إنحسار (Squeeze)"
        
        st.metric("التقلب (Bollinger)", volatility_status)
        if is_squeeze:
            st.caption("استعد لحركة سعرية عنيفة قريباً.")
