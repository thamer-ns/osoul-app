import yfinance as yf
import streamlit as st
import pandas as pd
from config import TADAWUL_DB

def get_ticker_symbol(symbol):
    # إذا كان رقم، نضيف له .SR (سعودي)
    # إذا كان حروف، نتركه كما هو (أمريكي/عملات)
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    s_clean = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    # البحث في قاعدة البيانات السعودية
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
    # إذا كان رمزاً أجنبياً
    return f"{s_clean}", "سوق عالمي/أخرى"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data(symbols_list):
    if not symbols_list: return {}
    tickers_map = {s: get_ticker_symbol(s) for s in symbols_list}
    unique = list(set(tickers_map.values()))
    results = {}
    
    if unique:
        try:
            # جلب البيانات
            df = yf.download(unique, period="2d", group_by='ticker', progress=False)
            
            for original, yahoo_sym in tickers_map.items():
                try:
                    # التعامل مع الـ MultiIndex المعقد
                    if len(unique) > 1:
                        if yahoo_sym in df.columns.levels[0]: # تأكد أن السهم موجود
                            stock_data = df[yahoo_sym]
                        else: continue
                    else:
                        stock_data = df # سهم واحد
                    
                    # تنظيف البيانات
                    if stock_data.empty: continue
                    
                    # استخراج آخر سعر
                    # بعض إصدارات ياهو تعيد السطر الأخير فارغاً أحياناً
                    stock_data = stock_data.dropna(subset=['Close'])
                    
                    if not stock_data.empty:
                        last_price = float(stock_data['Close'].iloc[-1])
                        
                        # حساب الإغلاق السابق
                        if len(stock_data) > 1:
                            prev_close = float(stock_data['Close'].iloc[-2])
                        else:
                            prev_close = last_price # إذا بيانات يوم واحد فقط
                        
                        if last_price > 0:
                            results[original] = {
                                'price': last_price,
                                'prev_close': prev_close,
                                'year_high': last_price, 
                                'year_low': last_price,
                                'dividend_yield': 0.0
                            }
                except: continue
        except: pass
            
    return results

@st.cache_data(ttl=300)
def get_chart_history(symbol, period, interval):
    try:
        ticker = get_ticker_symbol(symbol)
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        
        if df is None or df.empty: return None
        
        # === الإصلاح الجوهري للانهيار (Flatten MultiIndex) ===
        # إذا كانت الأعمدة معقدة (مثل: Close -> LCID)، نحولها لبسيطة (Close)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # التأكد من وجود عمود Close
        if 'Close' not in df.columns and 'Adj Close' in df.columns:
            df['Close'] = df['Adj Close']
            
        return df
    except: return None

@st.cache_data(ttl=300)
def get_tasi_data():
    try:
        df = yf.download("^TASI.SR", period="5d", progress=False)
        
        # تنظيف الأعمدة للمؤشر أيضاً
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if not df.empty:
            df = df.dropna(subset=['Close'])
            last = df['Close'].iloc[-1]
            prev = df['Close'].iloc[-2]
            change = ((last - prev) / prev) * 100
            return float(last), float(change)
    except: pass
    return 0.0, 0.0
