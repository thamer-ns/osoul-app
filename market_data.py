import requests
from bs4 import BeautifulSoup
import streamlit as st
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 1. جلب السعر المباشر (Google Finance) ===
def get_ticker_symbol(symbol):
    """تنظيف الرمز"""
    return str(symbol).replace('.SR', '').replace('.sr', '').strip()

def fetch_price_from_google(symbol):
    ticker = get_ticker_symbol(symbol)
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # تقليل المهلة (timeout) لتسريع الفشل إذا علق الطلب
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if price_div:
                return float(price_div.text.replace('SAR', '').replace(',', '').strip())
    except Exception as e:
        # لا نطبع الخطأ لتجنب تشويش الكونسول عند السرعة العالية
        pass
    return 0.0

# === 2. جلب الشارت (معطل مؤقتاً) ===
@st.cache_data(ttl=3600)
def get_chart_history(symbol, period='1y', interval='1d'):
    return None

# === 3. تحديث الأسعار الجماعي (Parallel Execution) ===
def fetch_batch_data(symbols_list):
    results = {}
    if not symbols_list: return results
    
    # استخدام ThreadPoolExecutor لتشغيل الطلبات بالتوازي
    # max_workers=10 يعني طلب 10 أسعار في نفس اللحظة
    with ThreadPoolExecutor(max_workers=10) as executor:
        # إرسال المهام
        future_to_symbol = {executor.submit(fetch_price_from_google, sym): sym for sym in symbols_list}
        
        # تجميع النتائج بمجرد وصولها
        for future in as_completed(future_to_symbol):
            sym = future_to_symbol[future]
            try:
                price = future.result()
                if price > 0:
                    results[sym] = {
                        'price': price,
                        'prev_close': price, # جوجل لا يعطي الإغلاق السابق بسهولة في نفس الصفحة، نستخدم الحالي مؤقتاً
                        'year_high': price,
                        'year_low': price,
                        'dividend_yield': 0.0
                    }
            except Exception as exc:
                print(f'{sym} generated an exception: {exc}')
                
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
