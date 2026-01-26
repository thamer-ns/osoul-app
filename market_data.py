import requests
from bs4 import BeautifulSoup
import streamlit as st
import yfinance as yf

def get_ticker_symbol(symbol):
    # تحويل الرمز لصيغة ياهو (1120 -> 1120.SR)
    s = str(symbol).strip()
    if s.isdigit(): return f"{s}.SR"
    if not s.endswith('.SR') and not s.startswith('.'): return f"{s}.SR"
    return s

def fetch_price_from_google(symbol):
    # Scraping Google (Fallback)
    ticker = symbol.replace('.SR', '')
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
    if symbol in ['.TASI', 'TASI']: url = "https://www.google.com/finance/quote/.TASI:TADAWUL"
    
    try:
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if div: return float(div.text.replace(',','').replace('SAR',''))
    except: pass
    return 0.0

@st.cache_data(ttl=300)
def get_tasi_data():
    price = fetch_price_from_google(".TASI")
    # لجلب التغير، ياهو أفضل
    try:
        tick = yf.Ticker("^TASI.SR")
        hist = tick.history(period="1d")
        if not hist.empty:
            p = hist['Close'].iloc[-1]
            prev = hist['Open'].iloc[-1] # تقريب
            chg = ((p - prev)/prev)*100
            return p, round(chg, 2)
    except: pass
    return price, 0.0

@st.cache_data(ttl=3600)
def get_chart_history(symbol, period='1y', interval='1d'):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        return t.history(period=period, interval=interval)
    except: return None

def fetch_batch_data(symbols_list):
    results = {}
    # نستخدم ياهو لأنه أسرع للكميات
    try:
        tickers = [get_ticker_symbol(s) for s in symbols_list]
        data = yf.download(tickers, period="1d", group_by='ticker', progress=False)
        
        for sym in symbols_list:
            ysym = get_ticker_symbol(sym)
            try:
                # التعامل مع هيكل بيانات ياهو المعقد
                if len(symbols_list) > 1:
                    row = data[ysym].iloc[-1]
                else:
                    row = data.iloc[-1]
                
                results[sym] = {
                    'price': row['Close'],
                    'prev_close': row['Open'], # تقريب
                    'year_high': row['High'],
                    'year_low': row['Low']
                }
            except: 
                # Fallback to Google
                p = fetch_price_from_google(sym)
                if p > 0: results[sym] = {'price': p, 'prev_close': p}
    except: pass
    return results

def get_static_info(symbol):
    from data_source import get_company_details
    n, s = get_company_details(symbol)
    return n or symbol, s or "سوق الأسهم"
