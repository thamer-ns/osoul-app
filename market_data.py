import requests
from bs4 import BeautifulSoup
import streamlit as st
import yfinance as yf
import pandas as pd
import random
import time

# ==============================
# 🛠️ Helpers & Configuration
# ==============================
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0'
]

def get_headers():
    return {'User-Agent': random.choice(USER_AGENTS)}

def get_ticker_symbol(symbol):
    s = str(symbol).strip().upper()
    if not s: return ""
    if s in ['TASI', '.TASI', '^TASI']: return '^TASI.SR'
    if s.isdigit(): return f"{s}.SR"
    if not s.endswith('.SR') and not s.startswith('^'): return f"{s}.SR"
    return s

def _safe_float(val):
    try:
        if isinstance(val, str):
            val = val.replace(',', '').replace('%', '').replace('SAR', '').strip()
        return float(val)
    except:
        return 0.0

# ==============================
# 1️⃣ Yahoo Finance
# ==============================
def fetch_from_yahoo(symbol):
    data = {}
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        info = t.info
        data['price'] = info.get('currentPrice') or info.get('regularMarketPrice')
        data['prev_close'] = info.get('previousClose')
        data['open'] = info.get('open')
        data['high'] = info.get('dayHigh')
        data['low'] = info.get('dayLow')
        data['volume'] = info.get('volume')
        data['pe_ratio'] = info.get('trailingPE')
        data['market_cap'] = info.get('marketCap')
        data['source'] = 'Yahoo'
    except:
        pass
    return data

# ==============================
# 2️⃣ Google Finance
# ==============================
def fetch_from_google(symbol):
    data = {}
    ticker = symbol.replace('.SR', '').replace('^', '')
    if ticker == '^TASI': ticker = '.TASI'
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
    try:
        r = requests.get(url, headers=get_headers(), timeout=4)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if div:
                data['price'] = _safe_float(div.text)
                data['source'] = 'Google'
    except:
        pass
    return data

# ==============================
# 3️⃣ Investing.com (محاولة)
# ==============================
def fetch_from_investing(symbol):
    # نتركها فارغة كـ fallback خفيف، يمكن تطوير لاحقاً
    return {}

# ==============================
# 4️⃣ الدمج الذكي بين المصادر
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_comprehensive_data(symbol):
    y_data = fetch_from_yahoo(symbol)
    g_data = fetch_from_google(symbol)
    i_data = fetch_from_investing(symbol)

    final_data = {
        'price': y_data.get('price') or g_data.get('price') or i_data.get('price') or 0.0,
        'prev_close': y_data.get('prev_close') or 0.0,
        'high': y_data.get('high') or 0.0,
        'low': y_data.get('low') or 0.0,
        'volume': y_data.get('volume') or 0.0,
        'pe_ratio': y_data.get('pe_ratio') or 0.0,
        'source': y_data.get('source', 'None')
    }
    if g_data.get('price'):
        final_data['source'] += ' & Google'
    if i_data.get('price'):
        final_data['source'] += ' & Investing'

    # fallback: إذا Yahoo لم يعطي سعر
    if final_data['price'] == 0 and g_data.get('price'):
        final_data['price'] = g_data['price']
        final_data['prev_close'] = g_data['price']
        final_data['source'] = 'Google Only'
    
    return final_data

# ==============================
# 5️⃣ TASI
# ==============================
@st.cache_data(ttl=300, show_spinner=False)
def get_tasi_data():
    data = fetch_comprehensive_data("^TASI.SR")
    price = data.get('price', 0)
    prev = data.get('prev_close', 0)
    if price and prev:
        chg = ((price - prev) / prev) * 100
        return price, round(chg, 2)
    return 0.0, 0.0

# ==============================
# 6️⃣ الشارت التاريخي
# ==============================
@st.cache_data(ttl=3600, show_spinner=False)
def get_chart_history(symbol, period='1y', interval='1d'):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        df = t.history(period=period, interval=interval)
        return df if not df.empty else None
    except:
        return None

# ==============================
# 7️⃣ Batch Fetch
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_batch_data(symbols_list):
    results = {}
    for sym in symbols_list:
        try:
            data = fetch_comprehensive_data(sym)
            results[sym] = {
                'price': data['price'],
                'prev_close': data['prev_close'],
                'high': data['high'],
                'low': data['low'],
                'pe_ratio': data['pe_ratio'],
                'source': data['source']
            }
        except:
            continue
    return results

# ==============================
# 8️⃣ Static Info
# ==============================
def get_static_info(symbol):
    try:
        from data_source import get_company_details
        return get_company_details(symbol)
    except:
        return symbol, "سوق الأسهم"