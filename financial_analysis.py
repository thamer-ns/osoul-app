import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12) # تحديث كل 12 ساعة
def get_fundamental_ratios(symbol):
    """جلب البيانات المالية مع معالجة الأخطاء والقيم المفقودة"""
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        info = t.info
        
        # دالة مساعدة لجلب القيمة أو صفر في حال عدم وجودها
        def get_val(key):
            v = info.get(key)
            return v if v is not None else 0

        # استخراج البيانات (مع حماية ضد القيم الفارغة)
        pe = get_val('trailingPE')
        pb = get_val('priceToBook')
        roe = get_val('returnOnEquity')
        eps = get_val('trailingEps')
        bv = get_val('bookValue')
        
        # محاولة جلب السعر من عدة مصادر
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or t.fast_info.last_price
        if not current_price: current_price = 0

        # حساب القيمة العادلة (Graham Number)
        # Fair Value = Sqrt(22.5 * EPS * BookValue)
        fair_value = 0
        if eps > 0 and bv > 0:
            fair_value = (22.5 * eps * bv) ** 0.5

        # حساب النسبة للمؤشر
        price_to_fair = 0
        if fair_value > 0:
            price_to_fair = current_price / fair_value

        return {
            "P/E": pe,
            "P/B": pb,
            "ROE": roe * 100 if roe else 0,
            "EPS": eps,
            "Book_Value": bv,
            "Fair_Value": fair_value,
            "Current_Price": current_price,
            "Price_to_Fair": price_to_fair
        }
    except Exception as e:
        # في حال الفشل التام، نعيد قاموساً باصفار بدلاً من None لتجنب انهيار الواجهة
        return {
            "P/E": 0, "P/B": 0, "ROE": 0, "EPS": 0, 
            "Book_Value": 0, "Fair_Value": 0, 
            "Current_Price": 0, "Price_to_Fair": 0
        }
