import yfinance as yf
import streamlit as st
from config import TADAWUL_DB

HAS_YF = True

def get_ticker_symbol(symbol):
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    s = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    info = TADAWUL_DB.get(s, {})
    return info.get('name', s), info.get('sector', 'أخرى')

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data(symbols_list):
    if not symbols_list: return {}
    tickers_map = {s: get_ticker_symbol(s) for s in symbols_list}
    unique = list(set(tickers_map.values()))
    results = {}
    
    batch_size = 10 
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i+batch_size]
        try:
            tickers = yf.Tickers(' '.join(batch))
            for orig, yahoo in tickers_map.items():
                if yahoo in batch:
                    try:
                        t = tickers.tickers[yahoo]
                        price = t.fast_info.last_price or t.info.get('currentPrice')
                        if price:
                            results[orig] = {
                                'price': float(price),
                                'prev_close': float(t.fast_info.previous_close),
                                'year_high': float(t.fast_info.year_high),
                                'year_low': float(t.fast_info.year_low),
                                'dividend_yield': float(t.info.get('dividendYield', 0) or 0)
                            }
                    except: pass
        except: pass
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
        t = yf.Ticker("^TASI.SR").fast_info
        return t.last_price, ((t.last_price - t.previous_close) / t.previous_close) * 100
    except: return 0.0, 0.0
