import yfinance as yf
import requests
from bs4 import BeautifulSoup
import streamlit as st
import time
from data_source import TADAWUL_DB

# === أدوات مساعدة ===
def get_ticker_yahoo(symbol):
    clean = str(symbol).replace('.SR', '').replace('.0', '').strip()
    return f"{clean}.SR"

def get_ticker_google(symbol):
    clean = str(symbol).replace('.SR', '').replace('.0', '').strip()
    return f"{clean}:TADAWUL"

def get_static_info(symbol):
    clean = str(symbol).replace('.SR', '').replace('.0', '').strip()
    data = TADAWUL_DB.get(clean)
    if data: return data['name'], data['sector']
    return symbol, "غير محدد"

# === المصدر 1: Yahoo Finance (سريع ويدعم الدفعات) ===
def fetch_from_yahoo_batch(symbols):
    results = {}
    if not symbols: return results
    
    tickers = [get_ticker_yahoo(s) for s in symbols]
    tickers_str = " ".join(tickers)
    
    try:
        data = yf.Tickers(tickers_str)
        for sym in symbols:
            ysym = get_ticker_yahoo(sym)
            try:
                info = data.tickers[ysym].fast_info
                price = info.last_price
                prev = info.previous_close
                if price and price > 0:
                    results[sym] = {'price': price, 'prev_close': prev, 'source': 'Yahoo'}
            except: pass
    except Exception as e:
        print(f"Yahoo Batch Error: {e}")
    return results

# === المصدر 2: Google Finance (احتياطي دقيق) ===
def fetch_from_google_single(symbol):
    url = f"https://www.google.com/finance/quote/{get_ticker_google(symbol)}"
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # فئات CSS قد تتغير، هذه الفئات الحالية للسعر
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if price_div:
                price = float(price_div.text.replace('SAR', '').replace(',', '').strip())
                return {'price': price, 'prev_close': price, 'source': 'Google'} # Google لا يعطي الإغلاق السابق بسهولة هنا
    except: pass
    return None

# === الدالة الرئيسية المدمجة (Hybrid Fetcher) ===
def fetch_batch_data(symbols_list):
    """
    يحاول جلب البيانات من ياهو أولاً، والأسهم التي تفشل يحاول جلبها من جوجل.
    """
    final_results = {}
    missing_symbols = []

    # 1. المحاولة الأولى: Yahoo Batch
    yahoo_res = fetch_from_yahoo_batch(symbols_list)
    
    for sym in symbols_list:
        if sym in yahoo_res and yahoo_res[sym]['price'] > 0:
            final_results[sym] = yahoo_res[sym]
        else:
            missing_symbols.append(sym)
    
    # 2. المحاولة الثانية: Google Finance (للمفقودين فقط)
    if missing_symbols:
        # print(f"Fetching backup for: {missing_symbols}") # للتجربة
        for sym in missing_symbols:
            google_res = fetch_from_google_single(sym)
            if google_res:
                final_results[sym] = google_res
            else:
                # إذا فشل المصدرين، نرجع أصفار
                final_results[sym] = {'price': 0.0, 'prev_close': 0.0, 'source': 'None'}
                
    return final_results

def get_tasi_data():
    # محاولة ياهو
    try:
        t = yf.Ticker("^TASI.SR")
        p = t.fast_info.last_price
        prev = t.fast_info.previous_close
        chg = ((p - prev)/prev)*100
        return p, chg
    except:
        # محاولة جوجل
        res = fetch_from_google_single(".TASI")
        if res: return res['price'], 0.0
        return 0.0, 0.0

def get_chart_history(symbol, period='1y', interval='1d'):
    try:
        t = yf.Ticker(get_ticker_yahoo(symbol))
        return t.history(period=period, interval=interval)
    except: return None
