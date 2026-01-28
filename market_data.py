import requests
from bs4 import BeautifulSoup
import streamlit as st
import yfinance as yf
import pandas as pd

# لتجاوز حظر جوجل
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def get_ticker_symbol(symbol):
    """توحيد صيغة الرموز"""
    s = str(symbol).strip().upper()
    if s in ['TASI', '.TASI', '^TASI']: return '^TASI.SR'
    if s.isdigit(): return f"{s}.SR"
    if not s.endswith('.SR') and not s.startswith('^'): return f"{s}.SR"
    return s

def fetch_price_from_google(symbol):
    """احتياطي: جلب السعر من جوجل"""
    try:
        ticker = symbol.replace('.SR', '')
        if ticker.startswith('^'): ticker = '.TASI'
        url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
        r = requests.get(url, headers=HEADERS, timeout=3)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if div: return float(div.text.replace(',', '').replace('SAR', '').strip())
    except: pass
    return 0.0

@st.cache_data(ttl=300)
def get_tasi_data():
    """بيانات المؤشر العام"""
    try:
        tick = yf.Ticker("^TASI.SR")
        hist = tick.history(period="5d")
        if not hist.empty:
            curr = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else hist['Open'].iloc[-1]
            chg = ((curr - prev) / prev) * 100
            return curr, round(chg, 2)
    except: pass
    return fetch_price_from_google(".TASI"), 0.0

@st.cache_data(ttl=3600)
def get_chart_history(symbol, period='1y', interval='1d'):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        df = t.history(period=period, interval=interval)
        return df if not df.empty else None
    except: return None

def fetch_batch_data(symbols_list):
    """جلب بيانات جماعية مع حساب دقيق لنسبة التغير"""
    results = {}
    if not symbols_list: return results
    clean_syms = [get_ticker_symbol(s) for s in symbols_list]
    
    try:
        data = yf.download(clean_syms, period="5d", group_by='ticker', progress=False, threads=True)
        for sym in symbols_list:
            ysym = get_ticker_symbol(sym)
            try:
                stock_data = data[ysym] if len(symbols_list) > 1 else data
                stock_data = stock_data.dropna()
                
                if not stock_data.empty:
                    curr = stock_data['Close'].iloc[-1]
                    prev = stock_data['Close'].iloc[-2] if len(stock_data) >= 2 else stock_data['Open'].iloc[-1]
                    results[sym] = {
                        'price': curr,
                        'prev_close': prev,
                        'year_high': stock_data['High'].max(),
                        'year_low': stock_data['Low'].min()
                    }
                else: raise Exception("Empty")
            except:
                p = fetch_price_from_google(sym)
                if p > 0: results[sym] = {'price': p, 'prev_close': p, 'year_high': 0, 'year_low': 0}
    except: pass
    return results

def get_static_info(symbol):
    from data_source import get_company_details
    n, s = get_company_details(symbol)
    return n or symbol, s or "سوق الأسهم"
