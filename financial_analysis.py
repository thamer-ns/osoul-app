import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """
    يقوم هذا الكود بحساب المؤشرات المالية يدوياً من القوائم المالية الخام (Raw Financials)
    لحل مشكلة عدم توفر البيانات الجاهزة للسوق السعودي.
    """
    ticker_sym = get_ticker_symbol(symbol)
    
    # تهيئة المتغيرات (أصفار افتراضية)
    data = {
        "P/E": 0.0, "P/B": 0.0, "ROE": 0.0, "EPS": 0.0, 
        "Book_Value": 0.0, "Current_Price": 0.0, "Fair_Value": 0.0,
        "Dividend_Yield": 0.0, "Debt_to_Equity": 0.0, "Profit_Margin": 0.0,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # ==========================================
        # 1. الحصول على السعر الحالي (Current Price)
        # ==========================================
        price = 0.0
        # محاولة 1: السعر اللحظي
        if hasattr(t, 'fast_info') and t.fast_info.last_price:
            price = float(t.fast_info.last_price)
        # محاولة 2: السجل التاريخي (أضمن طريقة)
        if price == 0:
            hist = t.history(period="5d")
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
        
        data["Current_Price"] = price
        if price == 0: return data # لا يمكن التحليل بدون سعر

        # ==========================================
        # 2. جلب البيانات الخام (القوائم المالية)
        # ==========================================
        info = t.info if t.info else {}
        
        # محاولة جلب عدد الأسهم (ضروري جداً للحساب)
        shares = info.get('sharesOutstanding')
        if not shares:
            # محاولة بديلة لعدد الأسهم
            try: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
            except: shares = 0

        # جلب صافي الدخل وحقوق المساهمين يدوياً
        net_income = 0.0
        total_equity = 0.0
        revenue = 0.0
        total_debt = 0.0

        try:
            # أ) قائمة الدخل (Income Statement)
            financials = t.financials
            if not financials.empty:
                # البحث عن صافي الدخل
                for key in ['Net Income', 'Net Income Common Stockholders', 'Net Income Continuous Operations']:
                    if key in financials.index:
                        net_income = financials.loc[key].iloc[0] # آخر سنة مالية
                        break
                # البحث عن المبيعات
                if 'Total Revenue' in financials.index:
                    revenue = financials.loc['Total Revenue'].iloc[0]
            
            # ب) الميزانية العمومية (Balance Sheet)
            balance = t.balance_sheet
            if not balance.empty:
                # حقوق المساهمين
                if 'Stockholders Equity' in balance.index:
                    total_equity = balance.loc['Stockholders Equity'].iloc[0]
                elif 'Total Assets' in balance.index and 'Total Liabilities Net Minority Interest' in balance.index:
                    total_equity = balance.loc['Total Assets'].iloc[0] - balance.loc['Total Liabilities Net Minority Interest'].iloc[0]
                
                # الديون
                if 'Total Debt' in balance.index:
                    total_debt = balance.loc['Total Debt'].iloc[0]

        except Exception as e:
            pass # استمر حتى لو فشل جلب القوائم

        # ==========================================
        # 3. الحسابات الرياضية (Manual Calculation)
        # ==========================================
        
        # --- حساب ربح السهم (EPS) ---
        if net_income != 0 and shares > 0:
            data["EPS"] = net_income / shares
        elif info.get('trailingEps'):
            data["EPS"] = float(info['trailingEps'])

        # --- حساب مكرر الربحية (P/E) ---
        # المعادلة: السعر / EPS
        if data["EPS"] > 0:
            data["P/E"] = price / data["EPS"]
        elif info.get('trailingPE'):
            data["P/E"] = float(info['trailingPE'])

        # --- حساب القيمة الدفترية (Book Value) ---
        if total_equity != 0 and shares > 0:
            data["Book_Value"] = total_equity / shares
        elif info.get('bookValue'):
            data["Book_Value"] = float(info['bookValue'])

        # --- حساب مكرر القيمة الدفترية (P/B) ---
        # المعادلة: السعر / القيمة الدفترية
        if data["Book_Value"] > 0:
            data["P/B"] = price / data["Book_Value"]
        elif info.get('priceToBook'):
            data["P/B"] = float(info['priceToBook'])

        # --- حساب العائد على حقوق الملكية (ROE) ---
        # المعادلة: (صافي الدخل / حقوق المساهمين) * 100
        if total_equity > 0 and net_income != 0:
            data["ROE"] = (net_income / total_equity) * 100
        elif info.get('returnOnEquity'):
            data["ROE"] = float(info['returnOnEquity']) * 100

        # --- حساب هامش الربح ---
        if revenue > 0:
            data["Profit_Margin"] = (net_income / revenue) * 100
        elif info.get('profitMargins'):
            data["Profit_Margin"] = float(info['profitMargins']) * 100

        # --- حساب المديونية ---
        if total_equity > 0:
            data["Debt_to_Equity"] = total_debt / total_equity
        elif info.get('debtToEquity'):
            data["Debt_to_Equity"] = float(info['debtToEquity'])

        # --- التوزيعات ---
        div_yield = info.get('dividendYield')
        data["Dividend_Yield"] = float(div_yield * 100) if div_yield else 0.0

        # ==========================================
        # 4. القيمة العادلة والتقييم الآلي
        # ==========================================
        
        # معادلة بنجامين غراهام المطورة
        if data["EPS"] > 0 and data["Book_Value"] > 0:
            data["Fair_Value"] = (22.5 * data["EPS"] * data["Book_Value"]) ** 0.5

        # نظام النقاط (Score System)
        score = 0
        opinions = []
        
        # تقييم P/E
        if 0 < data["P/E"] <= 15: score += 2; opinions.append("✅ مكرر ربحية ممتاز ومغري للشراء")
        elif 15 < data["P/E"] <= 25: score += 1; opinions.append("ℹ️ مكرر ربحية متوسط (سعر عادل)")
        elif data["P/E"] > 25: score -= 1; opinions.append("⚠️ مكرر ربحية مرتفع (السعر قد يكون متضخم)")
        
        # تقييم P/B
        if 0 < data["P/B"] <= 1.5: score += 1; opinions.append("✅ السهم يتداول بسعر قريب من قيمته الدفترية")
        
        # تقييم ROE
        if data["ROE"] > 15: score += 2; opinions.append("🔥 العائد على حقوق الملاك ممتاز جداً")
        elif data["ROE"] < 0: score -= 1; opinions.append("⚠️ الشركة تحقق خسائر (العائد سالب)")
        
        # تقييم التوزيعات
        if data["Dividend_Yield"] > 4: score += 1; opinions.append("💰 سهم عوائد (توزيعات مجزية)")
        
        # تقييم السعر العادل
        if data["Fair_Value"] > 0 and price < data["Fair_Value"]:
            diff = ((data['Fair_Value'] - price) / data['Fair_Value']) * 100
            score += 2; opinions.append(f"💎 فرصة: السعر الحالي أقل من القيمة العادلة بـ {diff:.1f}%")

        # النتيجة النهائية
        data["Score"] = max(0, min(10, 5 + score))
        if data["Score"] >= 8: data["Rating"] = "فرصة قوية ⭐"
        elif data["Score"] >= 6: data["Rating"] = "جيد / احتفاظ ✅"
        elif data["Score"] >= 4: data["Rating"] = "محايد 😐"
        else: data["Rating"] = "سلبي / حذر ❌"
        
        data["Opinions"] = opinions
        return data

    except Exception as e:
        return data
