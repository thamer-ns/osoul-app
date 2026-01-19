import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*24) # تخزين الكاش لمدة يوم كامل لأن البيانات المالية لا تتغير لحظياً
def get_fundamental_ratios(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        info = t.info
        
        # استخراج البيانات المالية
        pe_ratio = info.get('trailingPE', 0)
        pb_ratio = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0)
        eps = info.get('trailingEps', 0)
        book_value = info.get('bookValue', 0)
        debt_to_equity = info.get('debtToEquity', 0)
        current_price = info.get('currentPrice', 0) or info.get('regularMarketPrice', 0)

        # معادلة غراهام (نسخة مبسطة للقيمة العادلة)
        # Fair Value = Sqrt(22.5 * EPS * BookValue)
        fair_value = 0
        if eps > 0 and book_value > 0:
            fair_value = (22.5 * eps * book_value) ** 0.5

        return {
            "P/E": pe_ratio,
            "P/B": pb_ratio,
            "ROE": roe * 100 if roe else 0, # تحويل لنسبة مئوية
            "Debt/Eq": debt_to_equity,
            "EPS": eps,
            "Fair_Value": fair_value,
            "Price_to_Fair": (current_price / fair_value) if fair_value > 0 else 0
        }
    except Exception as e:
        return None
