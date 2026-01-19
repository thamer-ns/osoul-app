import yfinance as yf
import streamlit as st
import pandas as pd
from config import TADAWUL_DB

def get_ticker_symbol(symbol):
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    s_clean = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
    return f"سهم {s_clean}", "أخرى"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data(symbols_list):
    if not symbols_list: return {}
    tickers_map = {s: get_ticker_symbol(s) for s in symbols_list}
    unique = list(set(tickers_map.values()))
    results = {}
    
    # معالجة كل سهم على حدة لضمان الدقة (Batching أحياناً يضيع بعض الأسهم السعودية)
    for original_symbol, yahoo_symbol in tickers_map.items():
        try:
            t = yf.Ticker(yahoo_symbol)
            price = None
            prev_close = None
            
            # الطريقة المضمونة: السجل التاريخي
            hist = t.history(period="2d")
            
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price
            
            # محاولة احتياطية
            if not price and hasattr(t, 'fast_info'):
                price = t.fast_info.last_price
                prev_close = t.fast_info.previous_close

            if price and price > 0:
                results[original_symbol] = {
                    'price': float(price),
                    'prev_close': float(prev_close) if prev_close else float(price),
                    'year_high': float(t.fast_info.year_high) if hasattr(t, 'fast_info') else price,
                    'year_low': float(t.fast_info.year_low) if hasattr(t, 'fast_info') else price,
                    'dividend_yield': 0.0 # نتجاهل التوزيعات الآن لتسريع الجلب
                }
        except: continue
            
    return results

@st.cache_data(ttl=300)
def get_chart_history(symbol, period, interval):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        return t.history(period=period, interval=interval)
    except: return None

@st.cache_data(ttl=300)
def get_tasi_data():
    try:
        t = yf.Ticker("^TASI.SR")
        hist = t.history(period="5d")
        if not hist.empty:
            last = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else last
            change = ((last - prev) / prev) * 100
            return last, change
    except: pass
    return 0.0, 0.0
