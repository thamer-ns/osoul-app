import yfinance as yf
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*6) # تقليل مدة الكاش لـ 6 ساعات
def get_fundamental_ratios(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        info = t.info
        
        # 1. جلب السعر الحالي بأي طريقة
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not current_price and hasattr(t, 'fast_info'):
            current_price = t.fast_info.last_price
        if not current_price: current_price = 0

        # 2. جلب البيانات الأساسية
        pe = info.get('trailingPE')
        pb = info.get('priceToBook')
        eps = info.get('trailingEps')
        bv = info.get('bookValue')
        roe = info.get('returnOnEquity')

        # 3. الحساب اليدوي (Fallback) إذا كانت القيم مفقودة
        # إذا كان الـ P/E مفقوداً لكن السعر و EPS موجودين، نحسبه
        if (pe is None or pe == 0) and current_price > 0 and eps and eps > 0:
            pe = current_price / eps
        
        # إذا كان الـ P/B مفقوداً لكن السعر والقيمة الدفترية موجودين
        if (pb is None or pb == 0) and current_price > 0 and bv and bv > 0:
            pb = current_price / bv

        # تنظيف القيم النهائية (أصفار بدلاً من None)
        pe = pe if pe else 0
        pb = pb if pb else 0
        roe = (roe * 100) if roe else 0
        eps = eps if eps else 0
        bv = bv if bv else 0

        # 4. معادلة غراهام
        fair_value = 0
        if eps > 0 and bv > 0:
            fair_value = (22.5 * eps * bv) ** 0.5
            
        return {
            "P/E": pe,
            "P/B": pb,
            "ROE": roe,
            "EPS": eps,
            "Book_Value": bv,
            "Current_Price": current_price,
            "Fair_Value": fair_value
        }
    except Exception as e:
        # إرجاع أصفار آمنة
        return {
            "P/E": 0, "P/B": 0, "ROE": 0, "EPS": 0, 
            "Book_Value": 0, "Current_Price": 0, "Fair_Value": 0
        }
