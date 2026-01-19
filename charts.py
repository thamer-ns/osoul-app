import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from market_data import get_chart_history

# --- دالة حساب RSI (تم نقلها هنا لحل مشكلة الاستدعاء) ---
def calculate_rsi(data, window=14):
    try:
        if 'Close' not in data.columns: return None
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        
        # تجنب القسمة على صفر
        loss = loss.replace(0, 1)
        
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except: return None

def view_advanced_chart(fin):
    if 'custom_colors' not in st.session_state:
        # ألوان احتياطية في حال لم يتم تحميلها
        C = {
            'card_bg': '#FFFFFF',
            'main_text': '#1F2937',
            'primary': '#0e6ba8',
            'success': '#10B981',
            'danger': '#EF4444',
            'border': '#E5E7EB'
        }
    else:
        C = st.session_state.custom_colors

    trades = fin['all_trades']
    
    if trades.empty:
        st.info("أضف صفقات أولاً لعرض الرسم البياني")
        return

    c1, c2 = st.columns([1, 3])
    symbol = c1.selectbox("اختر السهم", trades['symbol'].unique())
    interval_ui = c1.selectbox("المدة", ["يومي (سنتين)", "أسبوعي (5 سنوات)", "ساعة (شهر)"])
    
    params = {"يومي (سنتين)": ("2y", "1d"), "أسبوعي (5 سنوات)": ("5y", "1wk"), "ساعة (شهر)": ("1mo", "60m")}
    
    if symbol:
        p, i = params[interval_ui]
        with c2:
            with st.spinner("جاري التحليل..."):
                df = get_chart_history(symbol, p, i)
            
            if df is not None and not df.empty:
                # التحليل الفني
                df['MA20'] = df['Close'].rolling(20).mean()
                df['MA50'] = df['Close'].rolling(50).mean()
                df['RSI'] = calculate_rsi(df)
                
                # إعداد الرسم البياني
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6, 0.2, 0.2])
                
                # 1. الشموع والمتوسطات
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#fbbf24', width=1), name='MA 20'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary'], width=1), name='MA 50'), row=1, col=1)
                
                # 2. الحجم (Volume)
                colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)
                
                # 3. مؤشر RSI
                if 'RSI' in df.columns:
                    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#A855F7', width=1.5), name='RSI'), row=3, col=1)
                    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
                    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)
                
                # تنسيق التصميم
                fig.update_layout(
                    height=700, 
                    xaxis_rangeslider_visible=False, 
                    paper_bgcolor=C['card_bg'], 
                    plot_bgcolor=C['card_bg'], 
                    font=dict(color=C['main_text'], family="Cairo"), 
                    margin=dict(l=10, r=10, t=10, b=10), 
                    showlegend=False
                )
                fig.update_xaxes(showgrid=True, gridcolor=C['border'])
                fig.update_yaxes(showgrid=True, gridcolor=C['border'])
                
                st.plotly_chart(fig, use_container_width=True)
            else: 
                st.warning("لا توجد بيانات متاحة لهذا السهم حالياً")
