import yfinance as yf
import streamlit as st
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
    
    # تقسيم الدفعات لتسريع العمل
    batch_size = 20
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i+batch_size]
        try:
            tickers_str = ' '.join(batch)
            data = yf.Tickers(tickers_str)
            for original_symbol, yahoo_symbol in tickers_map.items():
                if yahoo_symbol in batch:
                    try:
                        t = data.tickers[yahoo_symbol]
                        # محاولة جلب السعر بطرق متعددة لضمان عدم وجود أصفار
                        price = None
                        if hasattr(t, 'fast_info'): 
                            price = t.fast_info.last_price
                        
                        if price is None or price == 0:
                            hist = t.history(period="1d")
                            if not hist.empty: price = hist['Close'].iloc[-1]
                            
                        if price and price > 0:
                            results[original_symbol] = {
                                'price': float(price),
                                'prev_close': float(t.fast_info.previous_close) if hasattr(t, 'fast_info') else price,
                                'year_high': float(t.fast_info.year_high) if hasattr(t, 'fast_info') else price,
                                'year_low': float(t.fast_info.year_low) if hasattr(t, 'fast_info') else price,
                                'dividend_yield': float(t.info.get('dividendYield', 0) or 0)
                            }
                    except: continue
        except: continue
    return results

@st.cache_data(ttl=300)
def get_chart_history(symbol, period, interval):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        return t.history(period=period, interval=interval)
    except: return None

@st.cache_data(ttl=300)
def get_tasi_data():
    """
    دالة محسنة لجلب مؤشر تاسي وتجنب مشكلة الأصفار
    """
    try:
        # استخدام history بدلاً من fast_info لأنها أدق للمؤشرات
        ticker = yf.Ticker("^TASI.SR")
        hist = ticker.history(period="5d") # نجلب 5 أيام لضمان وجود بيانات
        
        if not hist.empty:
            last_price = hist['Close'].iloc[-1]
            # البحث عن سعر الإغلاق السابق
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
            else:
                prev_close = last_price # في حال عدم وجود سابق
            
            change_pct = ((last_price - prev_close) / prev_close) * 100
            return last_price, change_pct
            
    except Exception as e:
        pass
    
    return 0.0, 0.0
