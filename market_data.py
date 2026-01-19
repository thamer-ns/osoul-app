import yfinance as yf
import streamlit as st
from config import TADAWUL_DB

def get_ticker_symbol(symbol):
    """تحويل الرمز إلى صيغة ياهو فاينانس"""
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    """
    جلب معلومات الشركة (الاسم والقطاع)
    الأولوية: قاعدة البيانات المحلية المصححة (TADAWUL_DB)
    """
    s_clean = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    
    # البحث في قاعدتنا المحلية أولاً (الأدق)
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
    
    # إذا لم توجد، نعيد الرمز وقطاع غير محدد
    return f"سهم {s_clean}", "أخرى"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data(symbols_list):
    """جلب بيانات الأسعار فقط من السوق"""
    if not symbols_list: return {}
    
    # تنظيف الرموز
    tickers_map = {s: get_ticker_symbol(s) for s in symbols_list}
    unique_tickers = list(set(tickers_map.values()))
    results = {}
    
    batch_size = 20 # زيادة حجم الدفعة
    for i in range(0, len(unique_tickers), batch_size):
        batch = unique_tickers[i:i+batch_size]
        try:
            tickers_str = ' '.join(batch)
            data = yf.Tickers(tickers_str)
            
            for original_symbol, yahoo_symbol in tickers_map.items():
                if yahoo_symbol in batch:
                    try:
                        ticker_obj = data.tickers[yahoo_symbol]
                        # محاولة جلب السعر اللحظي أو سعر الإغلاق السابق
                        price = None
                        if hasattr(ticker_obj, 'fast_info'):
                            price = ticker_obj.fast_info.last_price
                        
                        if price is None:
                            price = ticker_obj.info.get('currentPrice')
                            
                        if price:
                            results[original_symbol] = {
                                'price': float(price),
                                'prev_close': float(ticker_obj.fast_info.previous_close),
                                'year_high': float(ticker_obj.fast_info.year_high),
                                'year_low': float(ticker_obj.fast_info.year_low),
                                'dividend_yield': float(ticker_obj.info.get('dividendYield', 0) or 0)
                            }
                    except Exception as e:
                        # في حال فشل جلب سهم معين، نتجاهله ولا نوقف البرنامج
                        continue
        except Exception as e:
            continue
            
    return results

@st.cache_data(ttl=300)
def get_chart_history(symbol, period, interval):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        return t.history(period=period, interval=interval)
    except: return None

@st.cache_data(ttl=300)
def get_tasi_data():
    try:
        t = yf.Ticker("^TASI.SR").fast_info
        return t.last_price, ((t.last_price - t.previous_close) / t.previous_close) * 100
    except: return 0.0, 0.0
