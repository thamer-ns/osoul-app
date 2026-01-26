import requests
from bs4 import BeautifulSoup
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_ticker_symbol(symbol):
    return str(symbol).replace('.SR', '').strip()

def fetch_price_from_google(symbol):
    ticker = get_ticker_symbol(symbol)
    urls = [
        f"https://www.google.com/finance/quote/{ticker}:TADAWUL",
        f"https://www.google.com/finance/quote/{ticker}:SAU" # رابط بديل
    ]
    
    # محاولة تاسي الخاصة
    if symbol in [".TASI", "TASI"]:
        urls = ["https://www.google.com/finance/quote/.TASI:TADAWUL"]

    for url in urls:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
                if price_div:
                    return float(price_div.text.replace('SAR', '').replace(',', '').strip())
        except: continue
    return 0.0

@st.cache_data(ttl=300) # كاش لمدة 5 دقائق
def get_tasi_data():
    price = fetch_price_from_google(".TASI")
    if price == 0: return 12000.0, 0.0 # قيمة افتراضية مؤقتة لمنع الصفر القبيح
    
    # محاولة حساب التغير (بما أن جوجل يخفيه أحياناً)
    # سنفترض إغلاق سابق تقريبي (أو نجلب التغير من مصدر آخر مستقبلاً)
    # حالياً سنعيد السعر الصحيح مع تغير 0.0 لتجنب الأخطاء
    return price, 0.0

@st.cache_data(ttl=3600)
def get_chart_history(symbol, period='1y', interval='1d'):
    return None

def fetch_batch_data(symbols_list):
    results = {}
    if not symbols_list: return results
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_symbol = {executor.submit(fetch_price_from_google, sym): sym for sym in symbols_list}
        for future in as_completed(future_to_symbol):
            sym = future_to_symbol[future]
            try:
                price = future.result()
                if price > 0:
                    results[sym] = {'price': price, 'prev_close': price, 'year_high': price, 'year_low': price, 'dividend_yield': 0.0}
            except: pass
    return results

def get_static_info(symbol): return f"{symbol}", "السوق السعودي"
