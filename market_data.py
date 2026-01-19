import yfinance as yf
import streamlit as st
import pandas as pd
from config import TADAWUL_DB

def get_ticker_symbol(symbol):
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    s_clean = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
    return f"سهم {s_clean}", "أخرى"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data(symbols_list):
    if not symbols_list: return {}
    tickers_map = {s: get_ticker_symbol(s) for s in symbols_list}
    unique = list(set(tickers_map.values()))
    results = {}
    
    # نستخدم yf.download لأنها أسرع في جلب مجموعة أسهم دفعة واحدة
    if unique:
        try:
            # جلب آخر يومين فقط
            df = yf.download(unique, period="2d", group_by='ticker', progress=False)
            
            for original, yahoo_sym in tickers_map.items():
                try:
                    # التعامل مع هيكل البيانات المعقد من yfinance
                    if len(unique) > 1:
                        stock_data = df[yahoo_sym]
                    else:
                        stock_data = df # إذا كان سهم واحد، الداتافريم يكون مباشراً
                    
                    if not stock_data.empty:
                        # آخر سعر إغلاق
                        last_price = float(stock_data['Close'].iloc[-1])
                        # الإغلاق السابق
                        prev_close = float(stock_data['Close'].iloc[-2]) if len(stock_data) > 1 else last_price
                        
                        if last_price > 0:
                            results[original] = {
                                'price': last_price,
                                'prev_close': prev_close,
                                'year_high': last_price, # بيانات تقريبية للسرعة
                                'year_low': last_price,
                                'dividend_yield': 0.0
                            }
                except: continue
        except: pass
            
    return results

@st.cache_data(ttl=300)
def get_chart_history(symbol, period, interval):
    try:
        # استخدام download للحصول على الداتا فريم مباشرة
        df = yf.download(get_ticker_symbol(symbol), period=period, interval=interval, progress=False)
        return df if not df.empty else None
    except: return None

@st.cache_data(ttl=300)
def get_tasi_data():
    """
    إصلاح المؤشر: استخدام download بدلاً من Ticker
    """
    try:
        # نجلب 5 أيام لضمان تجاوز العطلات
        df = yf.download("^TASI.SR", period="5d", progress=False)
        if not df.empty:
            last = df['Close'].iloc[-1]
            prev = df['Close'].iloc[-2]
            change = ((last - prev) / prev) * 100
            return float(last), float(change)
    except: 
        pass
    return 0.0, 0.0
