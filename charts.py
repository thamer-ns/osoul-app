import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from logic import get_chart_data, HAS_YF

def view_analysis(fin):
    C = st.session_state.custom_colors
    st.header("📈 التحليل الفني")
    
    # التحقق من وجود صفقات
    trades_df = fin.get('all_trades', None)
    trades_symbols = trades_df['symbol'].unique().tolist() if trades_df is not None and not trades_df.empty else []
    
    col_input, col_chart = st.columns([1, 3])
    
    with col_input:
        if not trades_symbols:
            st.info("لا توجد أسهم متاحة")
            return
        symbol = st.selectbox("اختر السهم:", trades_symbols)
        interval_ui = st.selectbox("الفاصل الزمني:", ["يومي (سنتين)", "أسبوعي (5 سنوات)", "ساعة (شهر)"])
        params_map = {"يومي (سنتين)": ("2y", "1d"), "أسبوعي (5 سنوات)": ("5y", "1wk"), "ساعة (شهر)": ("1mo", "60m")}

    if symbol:
        period, interval = params_map[interval_ui]
        with col_chart:
            with st.spinner(f"جاري تحليل {symbol}..."):
                df = get_chart_data(symbol, period, interval)
            
            if df is not None and not df.empty:
                df['MA20'] = df['Close'].rolling(window=20).mean()
                
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
                
                # الشموع
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
                # المتوسط
                fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#fbbf24', width=1.5), name='MA 20'), row=1, col=1)
                # الحجم
                colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)
                
                # --- الإصلاح هنا: إزالة الخط الرمادي (Spikes) ---
                fig.update_xaxes(showspikes=False, showgrid=True, gridcolor=C['border'])
                fig.update_yaxes(showspikes=False, showgrid=True, gridcolor=C['border'])
                
                fig.update_layout(
                    height=550, 
                    xaxis_rangeslider_visible=False,
                    paper_bgcolor=C['card_bg'],
                    plot_bgcolor=C['card_bg'],
                    font=dict(color=C['main_text'], family="Cairo"),
                    showlegend=False,
                    hovermode='x unified', # يبقي صندوق المعلومات
                    margin=dict(l=10, r=10, t=10, b=10)
                )
                
                st.plotly_chart(fig, use_container_width=True)
