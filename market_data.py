import pandas as pd
import requests
from bs4 import BeautifulSoup
from tvDatafeed import TvDatafeed, Interval
import streamlit as st
import time
import random

# تهيئة TradingView (وضع الضيف)
tv = TvDatafeed()

def get_ticker_symbol(symbol):
    """تنظيف الرمز (إزالة .SR)"""
    return str(symbol).replace('.SR', '').replace('.sr', '').strip()

# === 1. جلب السعر المباشر من Google Finance ===
def fetch_price_from_google(symbol):
    ticker = get_ticker_symbol(symbol)
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # البحث عن كلاس السعر (قد يتغير، لذا نستخدم الكلاس الشائع حالياً)
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if price_div:
                return float(price_div.text.replace('SAR', '').replace(',', '').strip())
    except Exception as e:
        print(f"Google Finance Error ({ticker}): {e}")
    return 0.0

# === 2. جلب الشارت من TradingView ===
@st.cache_data(ttl=3600)
def get_chart_history(symbol, period='1y', interval='1d'):
    ticker = get_ticker_symbol(symbol)
    try:
        # جلب 300 شمعة يومية (تقريباً سنة)
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_daily, n_bars=300)
        if df is not None and not df.empty:
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            df.index.name = 'Date'
            return df
    except Exception as e:
        print(f"TradingView Error: {e}")
    return None

# === 3. تحديث الأسعار الجماعي ===
def fetch_batch_data(symbols_list):
    results = {}
    if not symbols_list: return results
    
    for sym in symbols_list:
        price = fetch_price_from_google(sym)
        if price > 0:
            results[sym] = {
                'price': price,
                'prev_close': price, # قيمة تقريبية
                'year_high': price,  # قيمة تقريبية
                'year_low': price,   # قيمة تقريبية
                'dividend_yield': 0.0
            }
        # تأخير بسيط لتجنب الحظر
        time.sleep(random.uniform(0.1, 0.3))
    return results

def get_static_info(symbol):
    from data_source import TADAWUL_DB
    s_clean = get_ticker_symbol(symbol)
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
    return f"{s_clean}", "أخرى"

def get_tasi_data():
    price = fetch_price_from_google(".TASI")
    if price == 0: price = fetch_price_from_google("TASI")
    return price, 0.0
