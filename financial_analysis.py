import yfinance as yf
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """التحليل المالي الأساسي (Fundamental)"""
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        # استخدام info بحذر
        try: info = t.info
        except: info = {}
        
        # دالة مساعدة
        def val(k, default=0): return info.get(k, default) if info.get(k) is not None else default

        # جلب البيانات
        pe = val('trailingPE')
        pb = val('priceToBook')
        roe = val('returnOnEquity')
        eps = val('trailingEps')
        bv = val('bookValue')
        
        # محاولة جلب السعر
        price = val('currentPrice') or val('regularMarketPrice')
        if not price and hasattr(t, 'fast_info'):
            price = t.fast_info.last_price
        
        # معادلة غراهام
        fair_value = 0
        if eps > 0 and bv > 0:
            fair_value = (22.5 * eps * bv) ** 0.5
            
        return {
            "P/E": pe,
            "P/B": pb,
            "ROE": roe * 100 if roe else 0,
            "EPS": eps,
            "Book_Value": bv,
            "Current_Price": price or 0,
            "Fair_Value": fair_value
        }
    except:
        return None 
