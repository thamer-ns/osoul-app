# financial_analysis.py
import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*4) # كاش لمدة 4 ساعات
def get_fundamental_ratios(symbol):
    # تجهيز هيكل البيانات الفارغ
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, 
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Score": 0, 
        "Rating": "تحليل غير متاح", "Opinions": []
    }
    
    # تصحيح الرمز (إضافة .SR)
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    # --- المحاولة الأولى: جلب السعر (الأهم) ---
    try:
        # نحاول جلب آخر 5 أيام لضمان وجود إغلاق حتى لو كان اليوم عطلة
        hist = ticker.history(period="5d")
        if not hist.empty:
            metrics["Current_Price"] = float(hist['Close'].iloc[-1])
        else:
            # محاولة أخيرة عبر fast_info
            if hasattr(ticker, 'fast_info') and ticker.fast_info.last_price:
                 metrics["Current_Price"] = ticker.fast_info.last_price
    except Exception as e:
        st.error(f"خطأ في جلب السعر: {e}")

    # إذا لم نجد سعراً، فلا داعي للإكمال
    if metrics["Current_Price"] == 0:
        metrics["Rating"] = "السعر غير متاح"
        metrics["Opinions"].append("⚠️ لم يتم العثور على بيانات تداول لهذا الرمز.")
        metrics["Opinions"].append("تأكد أن الرمز صحيح (مثال: 1120)")
        return metrics

    # --- المحاولة الثانية: جلب البيانات المالية ---
    try:
        info = ticker.info
        if not info: info = {} # حماية من القيمة None
        
        # استخراج البيانات الأساسية
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        metrics["P/E"] = info.get('trailingPE')
        metrics["P/B"] = info.get('priceToBook')
        metrics["ROE"] = info.get('returnOnEquity', 0)
        if metrics["ROE"]: metrics["ROE"] *= 100
        
        metrics["Dividend_Yield"] = info.get('dividendYield')
        if metrics["Dividend_Yield"]: metrics["Dividend_Yield"] *= 100

        # --- الحساب اليدوي (الخطة ب) ---
        # إذا كان Yahoo لا يعطي P/E جاهز، نحسبه نحن
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]
            
        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = metrics["Current_Price"] / metrics["Book_Value"]

        # حساب القيمة العادلة (Graham Number)
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except Exception as e:
        metrics["Opinions"].append(f"⚠️ بيانات مالية ناقصة: {str(e)}")

    # --- نظام التقييم (Scoring) ---
    score = 0
    ops = []
    
    # تقييم السعر مقارنة بالعادلة
    if metrics["Fair_Value"]:
        if metrics["Current_Price"] < metrics["Fair_Value"]:
            diff = ((metrics['Fair_Value'] - metrics['Current_Price']) / metrics['Fair_Value']) * 100
            score += 3
            ops.append(f"💎 فرصة: أقل من العادلة بـ {diff:.1f}%")
        else:
            ops.append("⚖️ السعر أعلى من القيمة العادلة")
    else:
        ops.append("ℹ️ لا يمكن حساب القيمة العادلة (بيانات ناقصة)")

    # تقييم مكرر الربحية
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append(f"✅ مكرر ممتاز ({pe:.1f})")
        elif 15 < pe <= 22: score += 1; ops.append(f"👌 مكرر متوسط ({pe:.1f})")
        else: ops.append("⚠️ مكرر مرتفع")
    
    # النتيجة النهائية
    metrics["Score"] = score
    metrics["Opinions"] = ops
    
    if score >= 5: metrics["Rating"] = "إيجابي ✅"
    elif score >= 3: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "تحفظ ⚠️"
    
    # في حال فشل كل شيء ولكن السعر موجود
    if not ops and metrics["Current_Price"] > 0:
        metrics["Rating"] = "بيانات محدودة"
        metrics["Opinions"].append("السعر متاح، لكن القوائم المالية لم تُحدث من المصدر.")

    return metrics
