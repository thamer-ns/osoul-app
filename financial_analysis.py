import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """
    محرك التحليل المالي الذكي: يجلب البيانات من القوائم المالية مباشرة
    إذا لم تكن متوفرة في المعلومات السريعة.
    """
    ticker_sym = get_ticker_symbol(symbol)
    
    # هيكل البيانات الافتراضي (أصفار)
    data = {
        "P/E": 0.0, "P/B": 0.0, "ROE": 0.0, "EPS": 0.0, 
        "Book_Value": 0.0, "Current_Price": 0.0, 
        "Fair_Value": 0.0, "Price_to_Fair": 0.0,
        "Net_Income": 0.0, "Total_Equity": 0.0
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # 1. جلب السعر الحالي (Current Price) - الأولوية القصوى
        price = 0.0
        # محاولة 1: السعر اللحظي السريع
        if hasattr(t, 'fast_info') and t.fast_info.last_price:
            price = t.fast_info.last_price
        # محاولة 2: السعر من المعلومات
        if not price:
            price = t.info.get('currentPrice') or t.info.get('regularMarketPrice')
        # محاولة 3: آخر سعر إغلاق من التاريخ
        if not price:
            hist = t.history(period='2d')
            if not hist.empty:
                price = hist['Close'].iloc[-1]
        
        data["Current_Price"] = float(price) if price else 0.0

        # 2. محاولة جلب البيانات الجاهزة من (info)
        info = t.info if t.info else {}
        
        data["EPS"] = info.get('trailingEps') or 0.0
        data["Book_Value"] = info.get('bookValue') or 0.0
        data["P/E"] = info.get('trailingPE') or 0.0
        data["P/B"] = info.get('priceToBook') or 0.0
        data["ROE"] = (info.get('returnOnEquity') or 0.0) * 100

        # 3. الغوص العميق (Deep Dive): الحساب من القوائم المالية إذا كانت البيانات ناقصة
        # نلجأ لهذا الحل إذا كان الـ Book Value أو EPS يساوي صفر
        if data["Book_Value"] == 0 or data["EPS"] == 0:
            try:
                # جلب عدد الأسهم
                shares = info.get('sharesOutstanding')
                if not shares:
                    shares = t.get_shares_full(start="2024-01-01").iloc[-1]
                
                if shares and shares > 0:
                    # أ) حساب القيمة الدفترية من الميزانية (Total Assets - Total Liab)
                    balance_sheet = t.balance_sheet
                    if not balance_sheet.empty:
                        # حقوق المساهمين = الأصول - الخصوم
                        total_equity = balance_sheet.loc['Stockholders Equity'].iloc[0] if 'Stockholders Equity' in balance_sheet.index else 0
                        if total_equity == 0 and 'Total Assets' in balance_sheet.index and 'Total Liabilities Net Minority Interest' in balance_sheet.index:
                             total_equity = balance_sheet.loc['Total Assets'].iloc[0] - balance_sheet.loc['Total Liabilities Net Minority Interest'].iloc[0]
                        
                        if total_equity > 0:
                            data["Book_Value"] = total_equity / shares
                            data["P/B"] = data["Current_Price"] / data["Book_Value"] if data["Book_Value"] > 0 else 0

                    # ب) حساب ربح السهم (EPS) من قائمة الدخل
                    financials = t.financials
                    if not financials.empty and 'Net Income' in financials.index:
                        net_income = financials.loc['Net Income'].iloc[0] # آخر سنة
                        data["EPS"] = net_income / shares
                        data["P/E"] = data["Current_Price"] / data["EPS"] if data["EPS"] > 0 else 0
                        
                        # حساب العائد على حقوق الملكية (ROE) يدوياً
                        if total_equity > 0:
                            data["ROE"] = (net_income / total_equity) * 100

            except Exception as deep_err:
                # في حال فشل الحساب العميق، نكتفي بما وجدناه
                pass

        # 4. معادلة بنجامين غراهام للقيمة العادلة
        # Fair Value = Sqrt(22.5 * EPS * Book Value)
        if data["EPS"] > 0 and data["Book_Value"] > 0:
            data["Fair_Value"] = (22.5 * data["EPS"] * data["Book_Value"]) ** 0.5
        
        return data

    except Exception as e:
        return data
