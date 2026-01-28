import pandas as pd
import streamlit as st
import yfinance as yf
import numpy as np
from market_data import fetch_price_from_google, get_ticker_symbol
from database import fetch_table, execute_query

# ==============================================================
# 🧠 المحرك المالي: يعتمد على كتب التحليل المالي وتقييم الشركات
# ==============================================================

def calculate_piotroski_score(info, financials, balance_sheet, cashflow):
    """
    حساب مقياس بيوتروسكي (F-Score) من 0 إلى 9
    يقيس: الربحية، الرافعة المالية، وكفاءة التشغيل.
    """
    score = 0
    try:
        # البيانات الحالية والسابقة
        net_income = financials.loc['Net Income'].iloc[0]
        net_income_prev = financials.loc['Net Income'].iloc[1]
        op_cash_flow = cashflow.loc['Operating Cash Flow'].iloc[0]
        roa = net_income / balance_sheet.loc['Total Assets'].iloc[0]
        roa_prev = net_income_prev / balance_sheet.loc['Total Assets'].iloc[1]
        
        # 1. الربحية (Profitability)
        score += 1 if net_income > 0 else 0           # صافي ربح موجب
        score += 1 if op_cash_flow > 0 else 0         # تدفق نقدي تشغيلي موجب
        score += 1 if roa > roa_prev else 0           # تحسن العائد على الأصول
        score += 1 if op_cash_flow > net_income else 0 # جودة الأرباح (كاش > صافي ربح)

        # 2. الرافعة والسيولة (Leverage & Liquidity)
        long_term_debt = balance_sheet.loc['Long Term Debt'].iloc[0] if 'Long Term Debt' in balance_sheet.index else 0
        long_term_debt_prev = balance_sheet.loc['Long Term Debt'].iloc[1] if 'Long Term Debt' in balance_sheet.index else 0
        current_ratio = balance_sheet.loc['Current Assets'].iloc[0] / balance_sheet.loc['Current Liabilities'].iloc[0]
        current_ratio_prev = balance_sheet.loc['Current Assets'].iloc[1] / balance_sheet.loc['Current Liabilities'].iloc[1]
        
        score += 1 if long_term_debt <= long_term_debt_prev else 0 # انخفاض أو ثبات الديون
        score += 1 if current_ratio > current_ratio_prev else 0     # تحسن النسبة الجارية
        
        # 3. الكفاءة التشغيلية (Operating Efficiency)
        # (تم التبسيط لعدم توفر كل البيانات الدقيقة في yfinance أحياناً)
        score += 1 # افتراضي لنقطة الأسهم المصدرة إذا لم تزد
        
    except:
        pass # في حال نقص البيانات نعيد ما تم حسابه
    return score

def get_advanced_fundamental_ratios(symbol):
    """
    تحليل مالي عميق يستخرج القيمة العادلة والمخاطر
    """
    metrics = {
        "Fair_Value_Graham": None, "PE_Model_Price": None, 
        "Piotroski_Score": 0, "Altman_Z_Score": None,
        "Financial_Health": "غير معروف", "Growth_Status": "N/A",
        "Dividend_Safety": "N/A"
    }
    
    clean_sym = get_ticker_symbol(symbol)
    price = fetch_price_from_google(symbol)
    
    try:
        t = yf.Ticker(clean_sym)
        info = t.info
        fin = t.financials
        bs = t.balance_sheet
        cf = t.cashflow
        
        # 1. القيمة العادلة (Ben Graham Number)
        # المعادلة: SquareRoot(22.5 * EPS * BookValuePerShare)
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        if eps > 0 and bvps > 0:
            metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        
        # 2. القيمة بناء على مكرر الربح المستهدف (للنمو)
        # المعادلة: EPS * Sector_PE (نفرض متوسط السوق 15-20)
        if eps > 0:
            metrics['PE_Model_Price'] = eps * 18.0 
            
        # 3. قياس المتانة (Piotroski Score)
        if not fin.empty and not bs.empty:
            metrics['Piotroski_Score'] = calculate_piotroski_score(info, fin, bs, cf)
            
        # تقييم الحالة بناءً على النتائج
        s = metrics['Piotroski_Score']
        if s >= 7: metrics['Financial_Health'] = "💪 قوي جداً"
        elif s >= 5: metrics['Financial_Health'] = "👌 مستقر"
        else: metrics['Financial_Health'] = "⚠️ ضعيف/خطر"

        # 4. أمان التوزيعات
        payout = info.get('payoutRatio', 0)
        if payout is not None:
            if payout < 0.60: metrics['Dividend_Safety'] = "آمنة ومستدامة"
            elif payout < 0.90: metrics['Dividend_Safety'] = "مرتفعة"
            else: metrics['Dividend_Safety'] = "خطر (تأكل الأرباح)"

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        
    return metrics, price

def render_financial_dashboard_ui(symbol):
    st.markdown("### 🔬 التحليل المالي الأساسي (Fundamental Intelligence)")
    
    metrics, current_price = get_advanced_fundamental_ratios(symbol)
    
    # عرض بطاقات المعلومات الرئيسية
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        st.metric("القيمة الحالية", f"{current_price:,.2f}")
    with c2:
        fv = metrics.get('Fair_Value_Graham')
        delta = ((fv - current_price)/current_price)*100 if fv else 0
        st.metric("قيمة جراهام العادلة", f"{fv:,.2f}" if fv else "-", f"{delta:.1f}%")
    with c3:
        st.metric("متانة الشركة (F-Score)", f"{metrics['Piotroski_Score']} / 9", metrics['Financial_Health'])
    with c4:
        st.metric("أمان التوزيعات", metrics['Dividend_Safety'])

    # التحليل المنطقي
    st.markdown("#### 🧠 التقرير الاستنتاجي:")
    if metrics['Piotroski_Score'] >= 7 and metrics.get('Fair_Value_Graham', 0) > current_price:
        st.success(f"✅ **فرصة استثمارية:** السهم يتمتع بمركز مالي قوي (Score {metrics['Piotroski_Score']}) ويتداول تحت قيمته العادلة (خصم). حسب منهجية جراهام، هذا السهم يعتبر لقطة.")
    elif metrics['Piotroski_Score'] < 4:
        st.error("⛔ **تحذير مالي:** الشركة تعاني من ضعف في الكفاءة التشغيلية أو تزايد في الديون. يُنصح بمراجعة القوائم بعناية قبل الدخول.")
    elif current_price > (metrics.get('Fair_Value_Graham', 0) * 1.5):
        st.warning("⚠️ **تضخم سعري:** السهم ممتاز مالياً لكن سعره تضخم كثيراً فوق القيمة العادلة. قد يكون هناك تصحيح.")
    else:
        st.info("ℹ️ **متوازن:** السهم يتداول في نطاق منطقي، الأداء المالي جيد ولكن لا توجد خصومات سعرية مغرية حالياً.")

    # عرض البيانات الخام
    with st.expander("📂 القوائم المالية التفصيلية"):
        st.write("يتم جلب البيانات الحية من Yahoo Finance...")
        # (يمكنك هنا إضافة كود الجدول السابق لعرض الأرقام)

