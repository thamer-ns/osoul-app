import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from market_data import get_chart_history
from config import DEFAULT_COLORS

def render_technical_chart(symbol, period='1y', interval='1d'):
    C = DEFAULT_COLORS; df = get_chart_history(symbol, period, interval)
    if df is None or len(df) < 50: st.warning("بيانات غير كافية"); return

    df['MA20'] = df['Close'].rolling(20).mean(); df['MA50'] = df['Close'].rolling(50).mean()
    df['STD20'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20']*2); df['BB_Lower'] = df['MA20'] - (df['STD20']*2)
    
    # RSI Correct Formula
    delta = df['Close'].diff(); gain = (delta.where(delta>0, 0)); loss = (-delta.where(delta<0, 0))
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss; df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    e12 = df['Close'].ewm(span=12, adjust=False).mean(); e26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = e12 - e26; df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']; df.dropna(inplace=True)

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.15, 0.2])
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='السعر'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color=C['primary']), name='MA50'), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=np.where(df['Close']>=df['Open'], '#26A69A', '#EF5350'), name='V'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", row=3, col=1); fig.add_hline(y=30, line_dash="dash", row=3, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['Hist'], marker_color=np.where(df['Hist']>=0, '#26A69A', '#EF5350'), name='H'), row=4, col=1)
    
    fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)
