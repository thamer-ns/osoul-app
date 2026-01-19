import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """
    محرك تحليل مالي ذكي:
    1. يصر على جلب السعر من التاريخ إذا فشل المباشر.
    2. يحسب المؤشرات (P/E, P/B) يدوياً من القوائم المالية.
    3. يعطي تقييماً ورأياً آلياً.
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
        
        # === 1. معركة البحث عن السعر (الأهم) ===
        price = 0.0
        # محاولة 1: السعر اللحظي
        if hasattr(t, 'fast_info') and t.fast_info.last_price:
            price = float(t.fast_info.last_price)
        
        # محاولة 2: السعر من المعلومات العامة
        if price == 0:
            price = t.info.get('currentPrice') or t.info.get('regularMarketPrice') or 0.0
            
        # محاولة 3: السجل التاريخي (الورقة الرابحة)
        if price == 0:
            # نجلب بيانات شهر كامل لنضمن وجود تداول
            hist = t.history(period="1mo")
            if not hist.empty:
                price = float(hist['Close'].iloc[-1]) # آخر سعر إغلاق متاح
        
        data["Current_Price"] = price

        # إذا لم نجد سعراً حتى الآن، نتوقف (الشركة قد تكون غير مدرجة أو الرمز خطأ)
        if price == 0: return None

        # === 2. جلب البيانات المالية الخام ===
        info = t.info if t.info else {}
        
        # نحاول استخدام القيم الجاهزة أولاً
        eps = info.get('trailingEps')
        bv = info.get('bookValue')
        pe = info.get('trailingPE')
        pb = info.get('priceToBook')
        roe = info.get('returnOnEquity')
        div_yield = info.get('dividendYield')
        debt_eq = info.get('debtToEquity')
        
        # === 3. الحساب اليدوي (الخطة ب) ===
        # إذا كانت القيم الجاهزة مفقودة، نحسبها بأنفسنا
        
        # حساب EPS ومكرر الربح
        if not eps or eps == 0:
            # نحاول جلب صافي الدخل وعدد الأسهم
            try:
                financials = t.financials
                if not financials.empty:
                    net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
                    shares = info.get('sharesOutstanding')
                    if not shares: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
                    
                    if shares and shares > 0:
                        eps = net_income / shares
            except: pass
            
        # إعادة حساب P/E بناءً على السعر الجديد و EPS
        if (not pe or pe == 0) and (eps and eps > 0):
            pe = price / eps

        # حساب القيمة الدفترية ومكررها
        if not bv or bv == 0:
            try:
                balance = t.balance_sheet
                if not balance.empty:
                    # حقوق المساهمين
                    equity = balance.loc['Stockholders Equity'].iloc[0] if 'Stockholders Equity' in balance.index else 0
                    shares = info.get('sharesOutstanding')
                    if equity > 0 and shares:
                        bv = equity / shares
            except: pass
            
        if (not pb or pb == 0) and (bv and bv > 0):
            pb = price / bv

        # تعبئة البيانات النهائية
        data["P/E"] = float(pe) if pe else 0.0
        data["P/B"] = float(pb) if pb else 0.0
        data["EPS"] = float(eps) if eps else 0.0
        data["Book_Value"] = float(bv) if bv else 0.0
        data["ROE"] = float(roe * 100) if roe else 0.0
        data["Dividend_Yield"] = float(div_yield * 100) if div_yield else 0.0
        data["Debt_to_Equity"] = float(debt_eq) if debt_eq else 0.0
        
        # هامش الربح
        if info.get('profitMargins'):
            data["Profit_Margin"] = float(info['profitMargins'] * 100)

        # === 4. القيمة العادلة (Graham) ===
        if data["EPS"] > 0 and data["Book_Value"] > 0:
            data["Fair_Value"] = (22.5 * data["EPS"] * data["Book_Value"]) ** 0.5

        # === 5. الذكاء الاصطناعي البسيط (التقييم) ===
        score = 0
        opinions = []
        
        # تقييم مكرر الربح
        if 0 < data["P/E"] <= 15:
            score += 2; opinions.append("✅ السهم مغري جداً (مكرر أرباح منخفض < 15)")
        elif 15 < data["P/E"] <= 25:
            score += 1; opinions.append("ℹ️ سعر السهم عادل (مكرر أرباح متوسط)")
        elif data["P/E"] > 25:
            score -= 1; opinions.append("⚠️ السهم قد يكون متضخماً (مكرر أرباح مرتفع)")
            
        # تقييم القيمة الدفترية
        if 0 < data["P/B"] <= 1.5:
            score += 1; opinions.append("✅ السهم يتداول قرب قيمته الدفترية")
            
        # تقييم العائد
        if data["ROE"] > 15:
            score += 2; opinions.append("🔥 إدارة الشركة ممتازة في توليد الأرباح (ROE > 15%)")
            
        # تقييم التوزيعات
        if data["Dividend_Yield"] > 4:
            score += 1; opinions.append(f"💰 الشركة توزع أرباحاً مجزية ({data['Dividend_Yield']:.1f}%)")
            
        # تقييم القيمة العادلة
        if data["Fair_Value"] > 0:
            if price < data["Fair_Value"]:
                score += 2; opinions.append(f"💎 السهم يتداول بأقل من قيمته العادلة بـ {((data['Fair_Value']-price)/data['Fair_Value']*100):.1f}%")
            else:
                opinions.append("📉 السعر الحالي أعلى من القيمة العادلة (غراهام)")

        # النتيجة النهائية
        data["Score"] = max(0, min(10, 5 + score)) # نضمن النتيجة بين 0 و 10
        
        if data["Score"] >= 8: data["Rating"] = "شراء قوي ⭐"
        elif data["Score"] >= 6: data["Rating"] = "شراء / احتفاظ ✅"
        elif data["Score"] >= 4: data["Rating"] = "محايد 😐"
        else: data["Rating"] = "بيع / حذر ❌"
        
        data["Opinions"] = opinions
        
        return data

    except Exception as e:
        return None
