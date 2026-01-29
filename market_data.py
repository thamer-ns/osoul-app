import requests
from bs4 import BeautifulSoup
import streamlit as st
import yfinance as yf
import pandas as pd
import time
import random

# ==============================
# 🛠️ إعدادات المتصفح الوهمي (للتمويه على المواقع)
# ==============================
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0'
]

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/'
    }

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
# 1️⃣ المصدر الأول: Yahoo Finance (الأكثر استقراراً)
# ==============================
def fetch_from_yahoo(symbol):
    data = {}
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        info = t.info
        # البيانات الأساسية
        data['price'] = info.get('currentPrice') or info.get('regularMarketPrice')
        data['prev_close'] = info.get('previousClose')
        data['open'] = info.get('open')
        data['high'] = info.get('dayHigh')
        data['low'] = info.get('dayLow')
        data['volume'] = info.get('volume')
        data['pe_ratio'] = info.get('trailingPE')
        data['market_cap'] = info.get('marketCap')
        data['source'] = 'Yahoo'
    except: pass
    return data

# ==============================
# 2️⃣ المصدر الثاني: Google Finance (سحب مباشر)
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
            
            # السعر الحالي
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if price_div: data['price'] = _safe_float(price_div.text)
            
            # محاولة جلب التغير والنسبة
            # ملاحظة: الكلاسات في جوجل تتغير، لذا نستخدم Yahoo كأساس وهذا كداعم
            data['source'] = 'Google'
    except: pass
    return data

# ==============================
# 3️⃣ المصدر الثالث: Investing.com (محاولة سحب)
# ==============================
def fetch_from_investing(symbol):
    # تنبيه: هذا الموقع يحارب الروبوتات بقوة، هذه محاولة "أفضل جهد"
    data = {}
    clean_sym = symbol.replace('.SR', '')
    # البحث عن الرابط قد يحتاج منطق معقد، هنا نفترض رابطاً مباشراً تقريبياً
    # للأسهم السعودية، الروابط تختلف. لذا سنجعله احتياطياً عاماً
    return data 

# ==============================
# 4️⃣ المصدر الرابع: تجميع ودمج (The Aggregator)
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_comprehensive_data(symbol):
    """
    العنكبوت المالي: يجمع البيانات من كل المصادر ويدمجها
    الأولوية: Yahoo -> Google -> أخرى
    """
    # 1. جلب من Yahoo
    y_data = fetch_from_yahoo(symbol)
    
    # 2. جلب من Google (لتعويض النقص أو التأكيد)
    g_data = fetch_from_google(symbol)
    
    # 3. الدمج الذكي (Consolidation)
    final_data = {
        'price': y_data.get('price') or g_data.get('price') or 0.0,
        'prev_close': y_data.get('prev_close') or 0.0,
        'high': y_data.get('high') or 0.0,
        'low': y_data.get('low') or 0.0,
        'volume': y_data.get('volume') or 0.0,
        'pe_ratio': y_data.get('pe_ratio') or 0.0,
        'source': y_data.get('source', 'None') + (' & Google' if g_data.get('price') else '')
    }
    
    # إذا فشل Yahoo ونجح Google في السعر
    if final_data['price'] == 0 and g_data.get('price'):
        final_data['price'] = g_data['price']
        final_data['prev_close'] = g_data['price'] # تقديري
        final_data['source'] = 'Google Only'

    return final_data

# ==============================
# 5️⃣ وظائف النظام الأساسية (لا تحذفها)
# ==============================

@st.cache_data(ttl=300, show_spinner=False)
def get_tasi_data():
    """المؤشر العام من مصادر متعددة"""
    data = fetch_comprehensive_data("^TASI.SR")
    price = data.get('price', 0)
    prev = data.get('prev_close', 0)
    if price and prev:
        chg = ((price - prev) / prev) * 100
        return price, round(chg, 2)
    return 0.0, 0.0

@st.cache_data(ttl=3600, show_spinner=False)
def get_chart_history(symbol, period='1y', interval='1d'):
    # الشارت حصرياً من Yahoo لدقته التاريخية
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        df = t.history(period=period, interval=interval)
        return df if not df.empty else None
    except: return None

@st.cache_data(ttl=60, show_spinner=False)
def fetch_batch_data(symbols_list):
    """جلب جماعي ذكي"""
    results = {}
    if not symbols_list: return results
    
    # 1. المحاولة السريعة (Batch Yahoo)
    try:
        tickers = [get_ticker_symbol(s) for s in symbols_list]
        data = yf.download(tickers, period="1d", group_by='ticker', progress=False, threads=True)
        
        for sym in symbols_list:
            ysym = get_ticker_symbol(sym)
            try:
                # التعامل مع اختلاف هيكل البيانات (سهم واحد vs متعدد)
                if len(tickers) > 1: row = data[ysym].iloc[-1]
                else: row = data.iloc[-1]
                
                results[sym] = {
                    'price': _safe_float(row.get('Close')),
                    'prev_close': _safe_float(row.get('Open')), # تقريبي
                    'year_high': _safe_float(row.get('High')),
                    'year_low': _safe_float(row.get('Low'))
                }
            except: pass
    except: pass

    # 2. تعبئة الفراغات (Google Loop)
    for sym in symbols_list:
        if sym not in results or results[sym]['price'] == 0:
            # إذا فشل Yahoo، نرسل العنكبوت لجوجل
            g_data = fetch_from_google(sym)
            if g_data.get('price'):
                results[sym] = {
                    'price': g_data['price'],
                    'prev_close': g_data['price'], # لا يوفر جوجل السابق بسهولة
                    'year_high': 0, 'year_low': 0
                }
    
    return results

def fetch_price_from_google(symbol):
    # دالة توافقية (Wrapper) للكود القديم
    d = fetch_from_google(symbol)
    return d.get('price', 0.0)
