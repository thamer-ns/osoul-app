# financial_analysis.py
import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    # 1. تجهيز القالب الافتراضي
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, 
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Debt_to_Equity": None, 
        "Profit_Margin": None, "Score": 0, 
        "Rating": "غير متاح", "Opinions": []
    }
    
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    try:
        # 2. محاولة جلب السعر (الطريقة السريعة والمضمونة)
        # fast_info عادة أدق وأسرع من info العادية
        if hasattr(ticker, 'fast_info') and 'last_price' in ticker.fast_info:
            metrics["Current_Price"] = ticker.fast_info['last_price']
        
        # محاولة بديلة للسعر إذا فشلت الأولى
        if metrics["Current_Price"] == 0:
            hist = ticker.history(period="1d")
            if not hist.empty:
                metrics["Current_Price"] = float(hist['Close'].iloc[-1])
        
        # إذا لم نجد سعراً، نتوقف فوراً
        if metrics["Current_Price"] == 0:
            metrics["Rating"] = "تعذر جلب السعر"
            return metrics

        # 3. جلب البيانات المالية (Info)
        info = ticker.info if ticker.info else {}
        
        # تعبئة البيانات المتاحة مباشرة
        metrics["P/E"] = info.get('trailingPE')
        metrics["P/B"] = info.get('priceToBook')
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        metrics["ROE"] = float(info.get('returnOnEquity', 0)) * 100 if info.get('returnOnEquity') else None
        metrics["Profit_Margin"] = float(info.get('profitMargins', 0)) * 100 if info.get('profitMargins') else None
        metrics["Debt_to_Equity"] = info.get('debtToEquity')
        
        div_yield = info.get('dividendYield')
        if div_yield: metrics["Dividend_Yield"] = div_yield * 100

        # 4. محاولات تعويض البيانات المفقودة (الذكاء البرمجي)
        # إذا كان EPS مفقوداً، نحاول حسابه من القوائم المالية
        if metrics["EPS"] is None:
            try:
                fin_df = ticker.financials
                shares = info.get('sharesOutstanding')
                if not fin_df.empty and shares:
                    # البحث عن صافي الدخل في الصفوف
                    net_income_row = fin_df.loc[fin_df.index.str.contains('Net Income', case=False, na=False)]
                    if not net_income_row.empty:
                        net_income = net_income_row.iloc[0, 0] # أحدث سنة
                        metrics["EPS"] = net_income / shares
            except: pass

        # إذا كان P/E مفقوداً، نحسبه يدوياً
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]

        # إذا كانت القيمة الدفترية مفقودة، نحاول حسابها
        if metrics["Book_Value"] is None:
            try:
                bs_df = ticker.balance_sheet
                shares = info.get('sharesOutstanding')
                if not bs_df.empty and shares:
                    # حقوق المساهمين
                    equity_row = bs_df.loc[bs_df.index.str.contains('Stockholder', case=False, na=False)]
                    if not equity_row.empty:
                        equity = equity_row.iloc[0, 0]
                        metrics["Book_Value"] = equity / shares
            except: pass

        # إذا كان P/B مفقوداً، نحسبه يدوياً
        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = metrics["Current_Price"] / metrics["Book_Value"]

        # 5. حساب القيمة العادلة (معادلة جراهام)
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            # Fair Value = Sqrt(22.5 * EPS * BookValue)
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

        # 6. نظام التقييم (Scoring Engine)
        score = 0
        opinions = []
        
        # تقييم مكرر الربحية
        if metrics["P/E"]:
            if 0 < metrics["P/E"] <= 15: 
                score += 3
                opinions.append(f"✅ مكرر ربحية ممتاز ومغري ({metrics['P/E']:.1f})")
            elif 15 < metrics["P/E"] <= 20: 
                score += 1
                opinions.append(f"👌 مكرر ربحية مقبول ({metrics['P/E']:.1f})")
            else:
                score -= 1
                opinions.append("⚠️ مكرر الربحية مرتفع")

        # تقييم مضاعف الدفترية
        if metrics["P/B"]:
            if 0 < metrics["P/B"] <= 1.5:
                score += 2
                opinions.append("✅ السهم يتداول قرب قيمته الدفترية")
            elif metrics["P/B"] > 4:
                score -= 1
        
        # تقييم القيمة العادلة
        if metrics["Fair_Value"]:
            if metrics["Current_Price"] < metrics["Fair_Value"]:
                diff = ((metrics['Fair_Value'] - metrics['Current_Price']) / metrics['Fair_Value']) * 100
                score += 3
                opinions.append(f"💎 جوهرة: السهم أقل من قيمته العادلة بـ {diff:.1f}%")
            else:
                opinions.append("⚖️ السعر الحالي أعلى من القيمة العادلة المحسوبة")

        # تقييم العائد على حقوق الملكية
        if metrics["ROE"] and metrics["ROE"] > 15:
            score += 1
            opinions.append(f"🔥 عائد حقوق ملكية قوي ({metrics['ROE']:.1f}%)")

        # حساب النتيجة النهائية
        final_score = max(0, min(10, 5 + score))
        metrics["Score"] = final_score
        metrics["Opinions"] = opinions

        if final_score >= 8: metrics["Rating"] = "شراء قوي ⭐"
        elif final_score >= 6: metrics["Rating"] = "إيجابي ✅"
        elif final_score >= 4: metrics["Rating"] = "احتفاظ 😐"
        else: metrics["Rating"] = "سلبي ❌"

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        
    return metrics
