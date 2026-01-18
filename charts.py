import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from logic import get_chart_data, HAS_YF

def view_analysis(fin):
    C = st.session_state.custom_colors
    st.header("📈 التحليل الفني")
    
    trades_symbols = fin['all_trades']['symbol'].unique().tolist() if not fin['all_trades'].empty else []
    
    c1, c2 = st.columns([1, 3])
    with c1:
        if not trades_symbols:
            st.info("لا توجد أسهم لعرضها")
            symbol = None
        else:
            symbol = st.selectbox("اختر السهم:", trades_symbols)
        interval_ui = st.selectbox("الفاصل الزمني:", ["يومي (سنتين)", "أسبوعي (5 سنوات)", "ساعة (شهر)"])
    
    params_map = {
        "يومي (سنتين)": ("2y", "1d"),
        "أسبوعي (5 سنوات)": ("5y", "1wk"),
        "ساعة (شهر)": ("1mo", "60m")
    }
    
    if symbol and HAS_YF:
        period, interval = params_map[interval_ui]
        with c2:
            with st.spinner(f"جاري تحليل {symbol}..."):
                df = get_chart_data(symbol, period, interval)
            if df is not None and not df.empty:
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA50'] = df['Close'].rolling(window=50).mean()
                
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#fbbf24', width=1.5), name='MA 20'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary'], width=1.5), name='MA 50'), row=1, col=1)
                
                colors = np.where(df['Close'] >= df['Open'], C['success'], C['danger'])
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='الحجم'), row=2, col=1)
                
                # إعدادات التخطيط العامة
                fig.update_layout(
                    height=600, 
                    xaxis_rangeslider_visible=False, 
                    paper_bgcolor=C['card_bg'], 
                    plot_bgcolor=C['card_bg'], 
                    font=dict(color=C['main_text'], family="Cairo"), 
                    margin=dict(l=10, r=10, t=10, b=10), 
                    showlegend=False, 
                    hovermode='x unified'
                )

                grid_color = C['border']
                
                # --- التعديل هنا: إضافة showspikes=False لإلغاء الخطوط عند التحويم ---
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor=grid_color, showspikes=False)
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor=grid_color, showspikes=False)
                
                st.plotly_chart(fig, use_container_width=True)
            else: st.warning("لا توجد بيانات")
    elif not HAS_YF: st.error("مكتبة yfinance غير مثبتة")
