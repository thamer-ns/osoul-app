import yfinance as yf
import streamlit as st
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
    
    batch_size = 20
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i+batch_size]
        try:
            tickers_str = ' '.join(batch)
            data = yf.Tickers(tickers_str)
            for original_symbol, yahoo_symbol in tickers_map.items():
                if yahoo_symbol in batch:
                    try:
                        t = data.tickers[yahoo_symbol]
                        # العودة للطريقة الكلاسيكية التي كانت تعمل
                        price = None
                        if hasattr(t, 'fast_info'): price = t.fast_info.last_price
                        if price is None: price = t.info.get('currentPrice')
                        
                        if price:
                            results[original_symbol] = {
                                'price': float(price),
                                'prev_close': float(t.fast_info.previous_close) if hasattr(t, 'fast_info') else price,
                                'year_high': float(t.fast_info.year_high) if hasattr(t, 'fast_info') else price,
                                'year_low': float(t.fast_info.year_low) if hasattr(t, 'fast_info') else price,
                                'dividend_yield': float(t.info.get('dividendYield', 0) or 0)
                            }
                    except: continue
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
        # الطريقة الأصلية التي كانت تعمل
        t = yf.Ticker("^TASI.SR").fast_info
        return t.last_price, ((t.last_price - t.previous_close) / t.previous_close) * 100
    except: return 0.0, 0.0
