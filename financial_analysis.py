import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12) # كاش لمدة 12 ساعة
def get_fundamental_ratios(symbol):
    """
    جلب البيانات المالية الأساسية وحساب القيمة العادلة (Graham Number)
    """
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        # نستخدم info لأنها تحتوي على البيانات المالية الدقيقة
        info = t.info
        
        # دالة مساعدة لتجنب الأخطاء إذا كان المفتاح غير موجود
        def get_val(key):
            val = info.get(key)
            return val if val is not None else 0

        # استخراج البيانات الحيوية
        pe = get_val('trailingPE')
        pb = get_val('priceToBook')
        roe = get_val('returnOnEquity')
        eps = get_val('trailingEps')
        bv = get_val('bookValue')
        
        # محاولة جلب السعر الحالي بأكثر من طريقة
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not current_price and hasattr(t, 'fast_info'):
            current_price = t.fast_info.last_price
        if not current_price: current_price = 0

        # --- حساب القيمة العادلة (معادلة بنجامين غراهام) ---
        # Fair Value = Sqrt(22.5 * EPS * Book Value)
        fair_value = 0
        if eps > 0 and bv > 0:
            fair_value = (22.5 * eps * bv) ** 0.5
        
        # تقييم السعر الحالي مقارنة بالعادلة
        price_to_fair = 0
        if fair_value > 0:
            price_to_fair = current_price / fair_value

        return {
            "P/E": pe,
            "P/B": pb,
            "ROE": roe * 100 if roe else 0, # تحويل لنسبة مئوية
            "EPS": eps,
            "Book_Value": bv,
            "Current_Price": current_price,
            "Fair_Value": fair_value,
            "Price_to_Fair": price_to_fair
        }
    except Exception as e:
        # في حال الفشل نرجع قاموساً بأصفار حتى لا يتوقف البرنامج
        return {
            "P/E": 0, "P/B": 0, "ROE": 0, "EPS": 0, 
            "Book_Value": 0, "Current_Price": 0, 
            "Fair_Value": 0, "Price_to_Fair": 0
        }
