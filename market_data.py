import requests
from bs4 import BeautifulSoup
import streamlit as st
import yfinance as yf
import pandas as pd
import time

# === START ADDITION: API Safety & Caching ===
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def get_ticker_symbol(symbol):
    """توحيد الرموز لتوافق Yahoo Finance"""
    s = str(symbol).strip().upper()
    if not s: return ""
    if s in ['TASI', '.TASI', '^TASI']: return '^TASI.SR'
    if s.isdigit(): return f"{s}.SR"
    if not s.endswith('.SR') and not s.startswith('^'): return f"{s}.SR"
    return s

def _safe_float(val):
    """تحويل آمن للأرقام"""
    try:
        return float(val)
    except:
        return 0.0

def fetch_price_from_google(symbol):
    """مصدر احتياطي (Scraping)"""
    ticker = symbol.replace('.SR', '').replace('^', '')
    if ticker == '^TASI': ticker = '.TASI'
    
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"
    try:
        # إضافة مهلة زمنية بسيطة لتجنب الحظر
        # time.sleep(0.5) 
        r = requests.get(url, headers=HEADERS, timeout=3)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if div:
                return _safe_float(div.text.replace(',', '').replace('SAR', '').strip())
    except Exception:
        pass
    return 0.0

@st.cache_data(ttl=300, show_spinner=False)
def get_tasi_data():
    """جلب بيانات المؤشر العام (كاش 5 دقائق)"""
    try:
        tick = yf.Ticker("^TASI.SR")
        # fast_info أسرع وأخف
        fi = tick.fast_info
        curr = fi.last_price
        prev = fi.previous_close
        if curr and prev:
            chg = ((curr - prev) / prev) * 100
            return _safe_float(curr), round(_safe_float(chg), 2)
    except:
        pass
    
    # محاولة البديل
    price = fetch_price_from_google(".TASI")
    return price, 0.0

@st.cache_data(ttl=3600, show_spinner=False)
def get_chart_history(symbol, period='1y', interval='1d'):
    """جلب الشارت التاريخي (كاش لمدة ساعة كاملة)"""
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        df = t.history(period=period, interval=interval)
        return df if not df.empty else None
    except:
        return None

@st.cache_data(ttl=120, show_spinner=False)
def fetch_batch_data(symbols_list):
    """
    جلب جماعي للأسعار (Batch Fetching).
    كاش دقيقتين لتقليل استدعاءات API.
    """
    results = {}
    if not symbols_list: return results
    
    clean_syms = list(set([get_ticker_symbol(s) for s in symbols_list]))
    
    # 1. محاولة Yahoo Batch
    try:
        if len(clean_syms) == 1:
            sym = clean_syms[0]
            fi = yf.Ticker(sym).fast_info
            results[sym.replace('.SR','')] = {
                'price': _safe_float(fi.last_price),
                'prev_close': _safe_float(fi.previous_close),
                'year_high': _safe_float(fi.year_high),
                'year_low': _safe_float(fi.year_low)
            }
        else:
            tickers = yf.Tickers(" ".join(clean_syms))
            for sym in clean_syms:
                try:
                    fi = tickers.tickers[sym].fast_info
                    orig_sym = sym.replace('.SR','')
                    results[orig_sym] = {
                        'price': _safe_float(fi.last_price),
                        'prev_close': _safe_float(fi.previous_close),
                        'year_high': _safe_float(fi.year_high),
                        'year_low': _safe_float(fi.year_low)
                    }
                except: pass
    except: pass

    # 2. تعبئة النواقص من Google
    for sym_raw in symbols_list:
        if sym_raw not in results:
            p = fetch_price_from_google(sym_raw)
            if p > 0:
                results[sym_raw] = {
                    'price': p, 'prev_close': p, 'year_high': 0, 'year_low': 0
                }
    
    return results

def get_static_info(symbol):
    try:
        from data_source import get_company_details
        return get_company_details(symbol)
    except:
        return symbol, "سوق الأسهم"
# === END ADDITION ===
