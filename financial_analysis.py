import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*24) # كاش لمدة يوم كامل لتسريع التصفح
def get_fundamental_ratios(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    
    data = {
        "P/E": 0.0, "P/B": 0.0, "ROE": 0.0, "EPS": 0.0, 
        "Book_Value": 0.0, "Current_Price": 0.0, "Fair_Value": 0.0,
        "Dividend_Yield": 0.0, "Debt_to_Equity": 0.0, "Profit_Margin": 0.0,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # 1. السعر (استخدام السجل التاريخي لأنه الأضمن)
        try:
            hist = t.history(period="5d")
            if not hist.empty:
                data["Current_Price"] = float(hist['Close'].iloc[-1])
            else:
                # محاولة احتياطية
                data["Current_Price"] = t.fast_info.last_price
        except: pass
        
        if data["Current_Price"] == 0: return data

        # 2. الحسابات اليدوية من القوائم (The Hard Way)
        # هذه الطريقة تتجاوز مشكلة "البيانات غير المتاحة" في واجهة ياهو
        try:
            balance_sheet = t.balance_sheet
            financials = t.financials
            info = t.info
            
            # أ) عدد الأسهم (ضروري جداً)
            shares = info.get('sharesOutstanding')
            if not shares:
                # قيمة تقريبية: القيمة السوقية / السعر
                mcap = info.get('marketCap')
                if mcap: shares = mcap / data["Current_Price"]
            
            if shares:
                # ب) ربح السهم (EPS)
                if not financials.empty:
                    # البحث عن صافي الدخل في الصفوف
                    net_income_row = None
                    for key in financials.index:
                        if 'Net Income' in str(key) and 'Common' not in str(key): # Common قد يسبب تكرار
                            net_income_row = key; break
                    
                    if net_income_row:
                        net_income = financials.loc[net_income_row].iloc[0]
                        data["EPS"] = net_income / shares
                        data["P/E"] = data["Current_Price"] / data["EPS"] if data["EPS"] > 0 else 0
                        
                        # هامش الربح
                        if 'Total Revenue' in financials.index:
                            rev = financials.loc['Total Revenue'].iloc[0]
                            data["Profit_Margin"] = (net_income / rev * 100) if rev > 0 else 0

                # ج) القيمة الدفترية (Book Value)
                if not balance_sheet.empty:
                    # البحث عن حقوق المساهمين
                    equity_row = None
                    for key in balance_sheet.index:
                        if 'Stockholders' in str(key) or 'Equity' in str(key):
                            equity_row = key; break
                    
                    if equity_row:
                        total_equity = balance_sheet.loc[equity_row].iloc[0]
                        data["Book_Value"] = total_equity / shares
                        data["P/B"] = data["Current_Price"] / data["Book_Value"] if data["Book_Value"] > 0 else 0
                        
                        # العائد على الحقوق ROE
                        if 'net_income' in locals() and total_equity > 0:
                            data["ROE"] = (net_income / total_equity) * 100
                    
                    # المديونية
                    if 'Total Debt' in balance_sheet.index and 'total_equity' in locals():
                        debt = balance_sheet.loc['Total Debt'].iloc[0]
                        data["Debt_to_Equity"] = debt / total_equity

            # د) التوزيعات (من Info لأنها عادة صحيحة)
            div = info.get('dividendYield', 0)
            data["Dividend_Yield"] = div * 100 if div else 0.0

        except Exception as calc_err:
            pass # في حال فشل الحساب اليدوي، نعتمد على الأصفار

        # 3. القيمة العادلة والتقييم
        if data["EPS"] > 0 and data["Book_Value"] > 0:
            data["Fair_Value"] = (22.5 * data["EPS"] * data["Book_Value"]) ** 0.5

        # تقييم
        score = 0
        opinions = []
        if 0 < data["P/E"] <= 15: score += 2; opinions.append("✅ مكرر ممتاز")
        if 0 < data["P/B"] <= 2: score += 1; opinions.append("✅ قيمة دفترية جيدة")
        if data["ROE"] > 10: score += 2; opinions.append("🔥 عائد ممتاز")
        if data["Dividend_Yield"] > 3: score += 1; opinions.append("💰 توزيعات جيدة")
        
        data["Score"] = max(0, min(10, 4 + score))
        if data["Score"] >= 7: data["Rating"] = "إيجابي ✅"
        elif data["Score"] >= 4: data["Rating"] = "محايد 😐"
        else: data["Rating"] = "سلبي ❌"
        
        data["Opinions"] = opinions
        return data

    except:
        return data
