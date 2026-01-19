import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*24) # تخزين الكاش لمدة 24 ساعة
def get_fundamental_ratios(symbol):
    """جلب البيانات المالية الأساسية وحساب القيمة العادلة"""
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        info = t.info
        
        # استخراج البيانات
        pe = info.get('trailingPE', 0)
        pb = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0)
        eps = info.get('trailingEps', 0)
        bv = info.get('bookValue', 0)
        current_price = info.get('currentPrice', 0) or info.get('regularMarketPrice', 0)

        # حساب القيمة العادلة (Graham Number)
        # Fair Value = Sqrt(22.5 * EPS * BookValue)
        fair_value = 0
        if eps is not None and bv is not None:
            if eps > 0 and bv > 0:
                fair_value = (22.5 * eps * bv) ** 0.5

        # حساب المسافة عن القيمة العادلة
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
        return None
