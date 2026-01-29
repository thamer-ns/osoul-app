import requests
from bs4 import BeautifulSoup
import streamlit as st
import yfinance as yf
import pandas as pd
import random

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
# 3️⃣ Investing.com Scraper (اختياري)
# ==============================
def fetch_from_investing(symbol):
    data = {}
    try:
        clean_sym = symbol.replace('.SR', '').upper()
        url = f"https://www.investing.com/equities/{clean_sym}-saudi-arabia"
        r = requests.get(url, headers=get_headers(), timeout=5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            div = soup.find('span', {'id': 'last_last'})
            if div:
                data['price'] = _safe_float(div.text)
                data['source'] = 'Investing'
    except:
        pass
    return data

# ==============================
# 4️⃣ الدمج الذكي بين المصادر
# ==============================
def fetch_comprehensive_data(symbol):
    sources = [fetch_from_yahoo, fetch_from_google, fetch_from_investing]
    final_data = {}
    used_sources = []

    for func in sources:
        d = func(symbol)
        if d.get('price'):
            for k, v in d.items():
                if k not in final_data or final_data[k] in [0, None]:
                    final_data[k] = v
            used_sources.append(d.get('source', 'Unknown'))

    final_data['source'] = ' & '.join(used_sources) if used_sources else 'None'

    # fallback: إذا لم يتم جلب السعر
    if final_data.get('price', 0) == 0:
        final_data['price'] = 0.0
        final_data['prev_close'] = 0.0
        final_data['high'] = 0.0
        final_data['low'] = 0.0
        final_data['volume'] = 0.0
        final_data['pe_ratio'] = 0.0

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
# 7️⃣ Batch Fetch (متوافق مع البرنامج القديم)
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_batch_data(symbols_list):
    results = {}
    for sym in symbols_list:
        try:
            data = fetch_comprehensive_data(sym)
            # ⚠️ فقط الحقول الأساسية لإبقاء التوافق
            results[sym] = {
                'price': data.get('price',0),
                'prev_close': data.get('prev_close',0),
                'year_high': data.get('high',0),
                'year_low': data.get('low',0)
            }
        except:
            continue
    return results

# ==============================
# 8️⃣ معلومات ثابتة
# ==============================
def get_static_info(symbol):
    try:
        from data_source import get_company_details
        return get_company_details(symbol)
    except:
        return symbol, "سوق الأسهم"

# ==============================
# 9️⃣ النسخة المتقدمة الاختيارية لكل سهم
# ==============================
def fetch_advanced_data(symbol):
    """جلب البيانات المتقدمة: PE, MarketCap, Volume, Source"""
    return fetch_comprehensive_data(symbol)