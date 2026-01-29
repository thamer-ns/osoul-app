import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from market_data import get_chart_history

# --- دالة مساعدة لحساب ورسم الدعم والمقاومة ---
def add_support_resistance(fig, df, sensitivity=3):
    levels = []
    # البحث عن القمم والقيعان المحلية
    for i in range(sensitivity, len(df) - sensitivity):
        # 1. اكتشاف قاع (Support)
        if df['Low'].iloc[i] < df['Low'].iloc[i-sensitivity:i].min() and \
           df['Low'].iloc[i] < df['Low'].iloc[i+1:i+sensitivity+1].min():
            level = df['Low'].iloc[i]
            if np.sum([abs(level - x) < level * 0.01 for x in [l[1] for l in levels]]) == 0:
                levels.append((df.index[i], level, "Support"))
                
        # 2. اكتشاف قمة (Resistance)
        if df['High'].iloc[i] > df['High'].iloc[i-sensitivity:i].max() and \
           df['High'].iloc[i] > df['High'].iloc[i+1:i+sensitivity+1].max():
            level = df['High'].iloc[i]
            if np.sum([abs(level - x) < level * 0.01 for x in [l[1] for l in levels]]) == 0:
                levels.append((df.index[i], level, "Resistance"))

    # رسم الخطوط
    for date, level, type_ in levels:
        color = '#00C853' if type_ == "Support" else '#D50000'
        fig.add_shape(type='line', x0=date, y0=level, x1=df.index[-1], y1=level,
                      line=dict(color=color, width=1, dash='dash'), xref='x', yref='y', row=1, col=1)

# --- الدالة الرئيسية ---
def render_technical_chart(symbol, period='2y', interval='1d'):
    # 1. جلب البيانات
    df = get_chart_history(symbol, period, interval)
    if df is None or len(df) < 200: 
        st.warning("البيانات التاريخية غير كافية للتحليل الفني الكامل.")
        return

    # 2. الحسابات الفنية (Technical Calculation)
    # المتوسطات
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    # Bollinger Bands
    df['STD_20'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['Close'].rolling(20).mean() + (df['STD_20'] * 2)
    df['BB_Lower'] = df['Close'].rolling(20).mean() - (df['STD_20'] * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['Close'].rolling(20).mean()
    
    # RSI
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

    # تجهيز البيانات للرسم (آخر 250 شمعة)
    plot_df = df.iloc[200:].copy()
    
    # 3. الرسم البياني (Plotting)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                        row_heights=[0.6, 0.2, 0.2],
                        subplot_titles=(f"السعر: {symbol}", "RSI", "MACD"))

    # الشموع
    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'],
                                 low=plot_df['Low'], close=plot_df['Close'], name='السعر'), row=1, col=1)
    
    # المتوسطات
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SMA_50'], line=dict(color='orange', width=1.5), name='SMA 50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SMA_200'], line=dict(color='#2962FF', width=2), name='SMA 200'), row=1, col=1)
    
    # البولنجر
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(0,0,255,0.05)', showlegend=False), row=1, col=1)

    # المؤشرات السفلية
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], line=dict(color='purple'), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    colors = np.where(plot_df['MACD_Hist'] >= 0, '#26a69a', '#ef5350')
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], marker_color=colors, name='Hist'), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], line=dict(color='blue'), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Signal_Line'], line=dict(color='orange'), name='Signal'), row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, hovermode='x unified', margin=dict(t=30, b=10, l=10, r=10))
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)

    # تفاعل: إظهار الدعم والمقاومة
    if st.checkbox("🎯 إظهار مستويات الدعم والمقاومة (Auto S&R)", value=False):
        add_support_resistance(fig, plot_df, sensitivity=3)

    st.plotly_chart(fig, use_container_width=True)

    # --- 4. التقرير الفني المفصل (John Murphy Logic) ---
    st.markdown("### 📋 التقرير الفني الذكي")
    
    # استخراج القيم الأخيرة
    last_close = df['Close'].iloc[-1]
    last_sma50 = df['SMA_50'].iloc[-1]
    last_sma200 = df['SMA_200'].iloc[-1]
    last_rsi = df['RSI'].iloc[-1]
    last_macd = df['MACD'].iloc[-1]
    last_signal = df['Signal_Line'].iloc[-1]
    
    # المتغيرات المنطقية للتحليل
    is_bull_market = last_close > last_sma200
    is_golden_cross = last_sma50 > last_sma200
    rsi_status = "neutral"
    if last_rsi > 70: rsi_status = "overbought"
    elif last_rsi < 30: rsi_status = "oversold"
    
    # 1. تحليل الاتجاه (Trend Analysis)
    st.markdown("##### 1️⃣ حالة الاتجاه (Trend):")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if is_bull_market:
            st.success(f"**إيجابي (سوق ثيران):** السعر الحالي ({last_close:.2f}) يتداول بثبات **فوق** متوسط 200 يوم ({last_sma200:.2f}). هذا يشير إلى اتجاه صاعد طويل المدى.")
        else:
            st.error(f"**سلبي (سوق دببة):** السعر الحالي ({last_close:.2f}) يتداول **تحت** متوسط 200 يوم ({last_sma200:.2f}). الحذر واجب، الاتجاه العام هابط.")
    
    with col_t2:
        if is_golden_cross:
            st.info("**الترتيب إيجابي:** المتوسط القصير (50) يتواجد فوق المتوسط الطويل (200). هذا يدعم استمرار الصعود.")
        else:
            st.warning("**الترتيب سلبي:** المتوسط القصير (50) يتواجد تحت المتوسط الطويل (200). هذا يضغط على السعر للهبوط.")

    # 2. تحليل الزخم والقوة (Momentum & Strength)
    st.markdown("##### 2️⃣ الزخم والمؤشرات (Momentum):")
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.write(f"**مؤشر القوة النسبية (RSI): {last_rsi:.1f}**")
        if rsi_status == "overbought":
            st.warning("⚠️ **تشبع شرائي:** السعر ارتفع بسرعة كبيرة. احتمالية التصحيح (جني الأرباح) عالية. لا ينصح بالشراء الآن.")
        elif rsi_status == "oversold":
            st.success("💎 **تشبع بيعي:** السعر انخفض كثيراً. قد تكون منطقة ارتداد جيدة للمضاربين (فرصة شراء محتملة).")
        else:
            st.info("⚖️ **منطقة حيادية:** الزخم طبيعي ومستقر. القرار يعتمد على اختراق المقاومة أو كسر الدعم.")

    with col_m2:
        st.write("**مؤشر الماكد (MACD):**")
        if last_macd > last_signal:
            st.success("🟢 **إشارة إيجابية:** خط الماكد يقطع خط الإشارة لأعلى (زخم صاعد متزايد).")
        else:
            st.error("🔴 **إشارة سلبية:** خط الماكد يقطع خط الإشارة لأسفل (بداية ضعف في الزخم).")

    # 3. الخلاصة (Verdict)
    st.markdown("---")
    st.markdown("##### 💡 الخلاصة الفنية:")
    
    # منطق التجميع للخلاصة
    score = 0
    if is_bull_market: score += 1
    if is_golden_cross: score += 1
    if last_macd > last_signal: score += 1
    if 30 < last_rsi < 70: score += 0.5 # استقرار
    elif last_rsi < 30: score += 1 # فرصة قاع
    
    if score >= 3.5:
        st.success("### ✅ النظرة العامة: إيجابية قوية (Strong Buy Area)")
        st.write("المؤشرات الفنية تدعم الصعود. الاتجاه العام صاعد والزخم إيجابي.")
    elif score <= 1:
        st.error("### ⛔ النظرة العامة: سلبية (Sell / Avoid)")
        st.write("المؤشرات تشير إلى ضعف وسيطرة البائعين. يفضل الانتظار خارج السوق.")
    else:
        st.warning("### ✋ النظرة العامة: حذر / ترقب (Hold)")
        st.write("هناك تضارب في الإشارات (ربما اتجاه صاعد ولكن زخم ضعيف، أو العكس). يفضل انتظار إشارة أوضح.")
