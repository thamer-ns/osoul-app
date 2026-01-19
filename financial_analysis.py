# financial_analysis.py
import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*24) # تحديث يومي فقط لتسريع النظام
def get_fundamental_ratios(symbol):
    """
    جلب البيانات المالية الأساسية وحساب القيمة العادلة (Graham Number)
    """
    ticker_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(ticker_sym)
        # استخدام fast_info أسرع أحياناً لكن info أدق للبيانات المالية
        info = t.info
        
        # استخراج البيانات الحيوية
        metrics = {
            "P/E": info.get('trailingPE', 0),
            "Forward P/E": info.get('forwardPE', 0),
            "P/B": info.get('priceToBook', 0),
            "ROE": (info.get('returnOnEquity', 0) or 0) * 100,
            "Dividend Yield": (info.get('dividendYield', 0) or 0) * 100,
            "Debt/Equity": info.get('debtToEquity', 0),
            "EPS": info.get('trailingEps', 0),
            "Book Value": info.get('bookValue', 0),
            "Current Price": info.get('currentPrice', 0) or info.get('regularMarketPrice', 0)
        }

        # --- حساب القيمة العادلة (معادلة بنجامين غراهام المطورة) ---
        # Fair Value = Sqrt(22.5 * EPS * Book Value)
        # الرقم 22.5 هو ناتج ضرب (مكرر ربحية 15) * (مكرر دفترية 1.5)
        metrics["Graham Fair Value"] = 0
        if metrics["EPS"] > 0 and metrics["Book Value"] > 0:
            metrics["Graham Fair Value"] = (22.5 * metrics["EPS"] * metrics["Book Value"]) ** 0.5
        
        # تقييم السعر الحالي مقارنة بالعادلة
        if metrics["Graham Fair Value"] > 0:
            metrics["Price/FairValue"] = metrics["Current Price"] / metrics["Graham Fair Value"]
        else:
            metrics["Price/FairValue"] = 0

        return metrics
    except Exception as e:
        return None
