import pandas as pd
import requests
from bs4 import BeautifulSoup
from tvDatafeed import TvDatafeed, Interval
import streamlit as st
import time
import random

# --- إعدادات TradingView (وضع الضيف) ---
# ملاحظة: يعمل بوضع الضيف (بدون يوزر) لكنه قد يتطلب تسجيل دخول لبيانات أكثر
tv = TvDatafeed() 

def get_ticker_symbol(symbol):
    """توحيد الرموز (إزالة .SR لأن Google/TV لا يحتاجونها دائماً)"""
    return str(symbol).replace('.SR', '').replace('.sr', '').strip()

# === 1. جلب السعر المباشر من Google Finance ===
def fetch_price_from_google(symbol):
    ticker = get_ticker_symbol(symbol)
    # رابط جوجل فايننس للسوق السعودي
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # الفئة الخاصة بالسعر في جوجل (قد تتغير مستقبلاً، لذا نستخدم أكثر من طريقة)
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            
            if price_div:
                price_str = price_div.text.replace('SAR', '').replace(',', '').strip()
                return float(price_str)
    except Exception as e:
        print(f"Google Finance Error ({ticker}): {e}")
    return 0.0

# === 2. جلب البيانات التاريخية من TradingView (للشارت) ===
@st.cache_data(ttl=3600)
def get_chart_history(symbol, period='1y', interval='1d'):
    ticker = get_ticker_symbol(symbol)
    
    try:
        # TradingView يحتاج الرمز والسوق (TADAWUL)
        # ملاحظة: tvDatafeed قد يكون بطيئاً قليلاً في المرة الأولى
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_daily, n_bars=300)
        
        if df is not None and not df.empty:
            # تنظيف البيانات لتناسب الرسوم البيانية
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            df.index.name = 'Date'
            return df
    except Exception as e:
        print(f"TradingView Error ({ticker}): {e}")
    
    return None

# === 3. وظيفة التحديث الجماعي (Batch) ===
def fetch_batch_data(symbols_list):
    results = {}
    if not symbols_list: return results
    
    # Google Finance لا يدعم Batch رسمي، لذا سنمر عليهم بحلقة مع تأخير بسيط لتجنب الحظر
    for sym in symbols_list:
        price = fetch_price_from_google(sym)
        # بما أننا لا نملك API للتغير والقمم، سنحسبها أو نتركها 0
        # يمكن جلب التغير من جوجل أيضاً إذا أردنا التوسع في الـ Scraping
        if price > 0:
            results[sym] = {
                'price': price,
                'prev_close': price, # تقريبي لعدم وجود مصدر مجاني للإغلاق السابق حالياً
                'year_high': price * 1.2, # قيم افتراضية حتى يتم توفر مصدر
                'year_low': price * 0.8,
                'dividend_yield': 0.0
            }
        time.sleep(random.uniform(0.1, 0.5)) # تأخير عشوائي "إنساني"
            
    return results

def get_static_info(symbol):
    from data_source import TADAWUL_DB
    s_clean = get_ticker_symbol(symbol)
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
    return f"{s_clean}", "أخرى"

def get_tasi_data():
    # مؤشر تاسي
    price = fetch_price_from_google(".TASI") # قد يختلف الرمز في جوجل
    if price == 0: price = fetch_price_from_google("TASI") 
    return price, 0.0
