import yfinance as yf
import pandas as pd
import streamlit as st
from data_source import TADAWUL_DB

# دالة مساعدة لتنظيف الرمز وإضافة .SR
def get_ticker_symbol(symbol):
    clean_sym = str(symbol).replace('.SR', '').replace('.0', '').strip()
    return f"{clean_sym}.SR"

def get_static_info(symbol):
    """جلب الاسم والقطاع من الملف المحلي"""
    clean_sym = str(symbol).replace('.SR', '').replace('.0', '').strip()
    data = TADAWUL_DB.get(clean_sym)
    if data:
        return data['name'], data['sector']
    return symbol, "غير محدد"

def fetch_batch_data(symbols_list):
    """جلب أسعار مجموعة أسهم دفعة واحدة بسرعة"""
    if not symbols_list: return {}
    
    # تحويل الرموز لصيغة ياهو (xxxx.SR)
    tickers = [get_ticker_symbol(s) for s in symbols_list]
    tickers_str = " ".join(tickers)
    
    results = {}
    try:
        # جلب البيانات دفعة واحدة
        data = yf.Tickers(tickers_str)
        
        for sym in symbols_list:
            y_sym = get_ticker_symbol(sym)
            try:
                # محاولة جلب المعلومات السريعة
                info = data.tickers[y_sym].fast_info
                price = info.last_price
                prev_close = info.previous_close
                
                # حساب التغير
                change_pct = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0
                
                if price > 0:
                    results[sym] = {
                        'price': price,
                        'prev_close': prev_close,
                        'change_pct': change_pct,
                        'year_high': info.year_high,
                        'year_low': info.year_low,
                        # العائد اختياري قد لا يكون متوفراً في fast_info
                        'dividend_yield': 0.0 
                    }
            except Exception as e:
                print(f"Error getting data for {sym}: {e}")
                # في حال الفشل، نضع قيماً صفرية ولا نوقف البرنامج
                results[sym] = {'price': 0.0, 'prev_close': 0.0, 'change_pct': 0.0, 'year_high': 0, 'year_low': 0, 'dividend_yield': 0}
                
    except Exception as e:
        st.error(f"فشل الاتصال بمصدر البيانات: {e}")
        
    return results

def get_tasi_data():
    """جلب مؤشر تاسي"""
    try:
        ticker = yf.Ticker("^TASI.SR")
        info = ticker.fast_info
        price = info.last_price
        prev = info.previous_close
        change = ((price - prev) / prev) * 100
        return price, change
    except:
        return 0.0, 0.0

def get_chart_history(symbol, period='1y', interval='1d'):
    """جلب بيانات الشارت"""
    try:
        ticker = yf.Ticker(get_ticker_symbol(symbol))
        df = ticker.history(period=period, interval=interval)
        return df
    except:
        return None
