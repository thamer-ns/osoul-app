import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from market_data import get_chart_history

def view_analysis(fin):
    st.header("📈 مركز التحليل الفني")
    
    # جلب الرموز من المحفظة والمتابعة
    trades_symbols = fin['all_trades']['symbol'].unique().tolist() if not fin['all_trades'].empty else []
    
    c1, c2 = st.columns([1, 3])
    with c1:
        st.markdown("**اختر السهم:**")
        symbol = st.selectbox("sym_chart", trades_symbols if trades_symbols else [], label_visibility="collapsed")
        
        st.markdown("**الفاصل الزمني:**")
        interval_ui = st.selectbox("int_chart", ["يومي (سنتين)", "أسبوعي (5 سنوات)", "ساعة (شهر)"], label_visibility="collapsed")
    
    params_map = {
        "يومي (سنتين)": ("2y", "1d"),
        "أسبوعي (5 سنوات)": ("5y", "1wk"),
        "ساعة (شهر)": ("1mo", "60m")
    }
    
    if symbol:
        period, interval = params_map[interval_ui]
        with c2:
            with st.spinner(f"جاري جلب بيانات {symbol}..."):
                df = get_chart_history(symbol, period, interval)
                
            if df is not None and not df.empty:
                # حساب المؤشرات البسيطة
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA50'] = df['Close'].rolling(window=50).mean()
                
                # رسم الشارت
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                
                # الشموع
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
                
                # المتوسطات
                fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#fbbf24', width=1), name='MA 20'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='#2563EB', width=1), name='MA 50'), row=1, col=1)
                
                # الحجم
                colors = np.where(df['Close'] >= df['Open'], '#10B981', '#EF4444')
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)
                
                fig.update_layout(height=500, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                
                # بيانات لحظية
                last_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                chg = ((last_price - prev_price)/prev_price)*100
                col = "green" if chg >= 0 else "red"
                st.markdown(f"<h3 style='text-align:center; color:{col};'>{last_price:.2f} ({chg:+.2f}%)</h3>", unsafe_allow_html=True)
                
            else:
                st.warning("تعذر جلب البيانات لهذا السهم.")
    else:
        st.info("الرجاء اختيار سهم لعرض التحليل.")
