import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """
    الإصدار الذهبي: يعتمد على البيانات التاريخية المضمونة (مثل Google Finance)
    لحساب المؤشرات يدوياً وتجنب الأصفار.
    """
    ticker_sym = get_ticker_symbol(symbol)
    
    # القيم الافتراضية
    data = {
        "P/E": 0.0, "P/B": 0.0, "ROE": 0.0, "EPS": 0.0, 
        "Book_Value": 0.0, "Current_Price": 0.0, "Fair_Value": 0.0,
        "Dividend_Yield": 0.0, "Debt_to_Equity": 0.0, "Profit_Margin": 0.0,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # === 1. الحصول على السعر (استراتيجية Google Finance) ===
        # نعتمد على سعر الإغلاق "المثبت" بدلاً من اللحظي المتقلب
        price = 0.0
        
        # الطريقة الأضمن: سجل آخر 5 أيام (تضمن وجود بيانات حتى لو السوق مغلق)
        hist = t.history(period="5d")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1]) # آخر سعر إغلاق
        
        # محاولة احتياطية فقط
        if price == 0:
            if hasattr(t, 'fast_info') and t.fast_info.last_price:
                price = float(t.fast_info.last_price)
            else:
                price = t.info.get('currentPrice') or t.info.get('regularMarketPrice') or 0.0
        
        data["Current_Price"] = price

        # إذا لم نجد سعراً، فلا يمكن التحليل
        if price == 0: return None

        # === 2. جلب البيانات المالية الخام (وليس المؤشرات الجاهزة) ===
        info = t.info if t.info else {}
        
        # نجلب عدد الأسهم (ضروري للحسابات)
        shares = info.get('sharesOutstanding')
        if not shares:
            try: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
            except: shares = 0

        # === 3. الحساب اليدوي "الإجباري" للمؤشرات ===
        # (لا نعتمد على ياهو في الحساب، نحسب بأنفسنا)
        
        # أ) حساب EPS ومكرر الربح (P/E)
        net_income = 0
        try:
            # محاولة جلب صافي الدخل من القوائم
            if not t.financials.empty:
                # نبحث عن أي مسمى لصافي الدخل
                for key in ['Net Income', 'Net Income Common Stockholders']:
                    if key in t.financials.index:
                        net_income = t.financials.loc[key].iloc[0] # السنة الأخيرة
                        break
        except: pass

        # إذا وجدنا الدخل والأسهم، نحسب EPS بأنفسنا
        if net_income > 0 and shares > 0:
            data["EPS"] = net_income / shares
        elif info.get('trailingEps'): # بديل جاهز
            data["EPS"] = float(info['trailingEps'])

        # حساب P/E
        if data["EPS"] > 0:
            data["P/E"] = price / data["EPS"]
        elif info.get('trailingPE'):
            data["P/E"] = float(info['trailingPE'])

        # ب) حساب القيمة الدفترية ومكررها (P/B)
        total_equity = 0
        try:
            if not t.balance_sheet.empty:
                if 'Stockholders Equity' in t.balance_sheet.index:
                    total_equity = t.balance_sheet.loc['Stockholders Equity'].iloc[0]
                elif 'Total Assets' in t.balance_sheet.index:
                    total_equity = t.balance_sheet.loc['Total Assets'].iloc[0] - t.balance_sheet.loc['Total Liabilities Net Minority Interest'].iloc[0]
        except: pass

        if total_equity > 0 and shares > 0:
            data["Book_Value"] = total_equity / shares
        elif info.get('bookValue'):
            data["Book_Value"] = float(info['bookValue'])

        # حساب P/B
        if data["Book_Value"] > 0:
            data["P/B"] = price / data["Book_Value"]
        elif info.get('priceToBook'):
            data["P/B"] = float(info['priceToBook'])

        # ج) باقي المؤشرات
        if total_equity > 0 and net_income > 0:
            data["ROE"] = (net_income / total_equity) * 100
        elif info.get('returnOnEquity'):
            data["ROE"] = float(info['returnOnEquity']) * 100

        div_yield = info.get('dividendYield')
        data["Dividend_Yield"] = float(div_yield * 100) if div_yield else 0.0
        
        debt = info.get('debtToEquity')
        data["Debt_to_Equity"] = float(debt) if debt else 0.0
        
        margins = info.get('profitMargins')
        data["Profit_Margin"] = float(margins * 100) if margins else 0.0

        # === 4. القيمة العادلة والتقييم ===
        if data["EPS"] > 0 and data["Book_Value"] > 0:
            data["Fair_Value"] = (22.5 * data["EPS"] * data["Book_Value"]) ** 0.5

        # نظام التقييم (Score)
        score = 0
        opinions = []
        
        # P/E Evaluation
        if 0 < data["P/E"] <= 15: score += 2; opinions.append("✅ مكرر ربحية ممتاز (< 15)")
        elif 15 < data["P/E"] <= 25: score += 1; opinions.append("ℹ️ مكرر ربحية متوسط")
        elif data["P/E"] > 25: score -= 1; opinions.append("⚠️ مكرر ربحية مرتفع")
        elif data["P/E"] == 0: opinions.append("⚪ الشركة لا تحقق أرباحاً حالياً")

        # P/B Evaluation
        if 0 < data["P/B"] <= 2: score += 1; opinions.append("✅ تتداول قرب القيمة الدفترية")
        
        # Fair Value Evaluation
        if data["Fair_Value"] > 0:
            if price < data["Fair_Value"]:
                diff = ((data['Fair_Value'] - price) / data['Fair_Value']) * 100
                score += 2; opinions.append(f"💎 أقل من القيمة العادلة بـ {diff:.1f}%")
            else:
                opinions.append("📉 السعر أعلى من القيمة العادلة")

        # Final Score
        data["Score"] = max(0, min(10, 5 + score))
        if data["Score"] >= 8: data["Rating"] = "شراء قوي ⭐"
        elif data["Score"] >= 6: data["Rating"] = "شراء ✅"
        elif data["Score"] >= 4: data["Rating"] = "احتفاظ 😐"
        else: data["Rating"] = "حذر ❌"
        
        data["Opinions"] = opinions
        return data

    except Exception as e:
        # إرجاع البيانات المحسوبة حتى اللحظة بدلاً من الفشل الكامل
        return data
