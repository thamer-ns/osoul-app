import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 📥 وحدة المزامنة: جلب البيانات وحفظها محلياً (Data Warehouse)
# ==============================================================

def sync_company_financials(symbol):
    """جلب القوائم المالية المفصلة وحفظها في قاعدة البيانات لتبقى كمرجع"""
    clean_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(clean_sym)
        
        # جلب القوائم الثلاثة
        inc = t.financials.T
        bs = t.balance_sheet.T
        cf = t.cashflow.T
        
        # دمج البيانات في جدول واحد بناءً على التاريخ
        # نستخدم أحدث 4 سنوات فقط لضمان السرعة
        all_dates = sorted(list(set(inc.index) | set(bs.index) | set(cf.index)), reverse=True)[:5]
        
        count = 0
        for date_val in all_dates:
            d_str = date_val.strftime('%Y-%m-%d')
            
            # استخراج البيانات بأمان (باستخدام .get لتجنب الأخطاء)
            # 1. قائمة الدخل
            rev = float(inc.loc[date_val].get('Total Revenue', 0)) if date_val in inc.index else 0
            net = float(inc.loc[date_val].get('Net Income', 0)) if date_val in inc.index else 0
            
            # 2. المركز المالي
            assets = 0; liab = 0; equity = 0; cur_ast = 0; cur_liab = 0; debt = 0
            if date_val in bs.index:
                row = bs.loc[date_val]
                assets = float(row.get('Total Assets', 0))
                liab = float(row.get('Total Liabilities Net Minority Interest', row.get('Total Liabilities', 0)))
                equity = float(row.get('Total Equity Gross Minority Interest', row.get('Total Equity', 0)))
                cur_ast = float(row.get('Current Assets', 0))
                cur_liab = float(row.get('Current Liabilities', 0))
                debt = float(row.get('Long Term Debt', 0))

            # 3. التدفق النقدي
            ocf = 0
            if date_val in cf.index:
                ocf = float(cf.loc[date_val].get('Operating Cash Flow', 0))

            # الحفظ في قاعدة البيانات (Upsert)
            query = """
                INSERT INTO "FinancialStatements" 
                (symbol, date, revenue, net_income, total_assets, total_liabilities, total_equity, 
                 operating_cash_flow, current_assets, current_liabilities, long_term_debt, period_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Annual')
                ON CONFLICT (symbol, date, period_type) 
                DO UPDATE SET 
                    revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income,
                    total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities,
                    total_equity=EXCLUDED.total_equity, operating_cash_flow=EXCLUDED.operating_cash_flow,
                    current_assets=EXCLUDED.current_assets, current_liabilities=EXCLUDED.current_liabilities,
                    long_term_debt=EXCLUDED.long_term_debt;
            """
            execute_query(query, (symbol, d_str, rev, net, assets, liab, equity, ocf, cur_ast, cur_liab, debt))
            count += 1
            
        return True, f"تم تحديث {count} سنوات"
    except Exception as e:
        return False, str(e)

# ==============================================================
# 🧠 وحدة التحليل: تقرأ من قاعدة البيانات (Offline First)
# ==============================================================

def get_stored_financials_df(symbol):
    """جلب البيانات التاريخية من الأرشيف المحلي"""
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            df = df[df['symbol'] == symbol].copy()
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date', ascending=False) # الأحدث أولاً
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    """
    التحليل المالي المتقدم (يعتمد على البيانات المحلية المحفوظة)
    """
    metrics = {
        "Fair_Value_Graham": None, "Piotroski_Score": 0,
        "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""
    }
    
    # 1. محاولة تحديث البيانات (Sync) إذا أمكن
    # لا نوقف التنفيذ لو فشل (نعتمد على القديم)
    sync_company_financials(symbol)
    
    # 2. قراءة البيانات من الأرشيف
    df = get_stored_financials_df(symbol)
    price = fetch_price_from_google(symbol)
    
    if df.empty or len(df) < 2:
        return metrics # بيانات غير كافية
    
    try:
        # البيانات الحالية (السنة الأخيرة) والسابقة
        curr = df.iloc[0]
        prev = df.iloc[1]
        
        # --- أ. حساب نموذج جراهام ---
        # نحتاج EPS و Book Value
        # بما أننا لا نخزن عدد الأسهم بدقة، سنستخدم القيم التقريبية من Yahoo للربحية للسهم
        # أو نستنتجها إذا توفر عدد الأسهم (سنعتمد على Yahoo info هنا كمكمل)
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps:
                metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass

        # --- ب. حساب Piotroski F-Score (من قاعدة البيانات المحلية) ---
        score = 0
        
        # 1. الربحية
        if curr['net_income'] > 0: score += 1
        if curr['operating_cash_flow'] > 0: score += 1
        
        roa_curr = curr['net_income'] / curr['total_assets'] if curr['total_assets'] else 0
        roa_prev = prev['net_income'] / prev['total_assets'] if prev['total_assets'] else 0
        if roa_curr > roa_prev: score += 1
        
        if curr['operating_cash_flow'] > curr['net_income']: score += 1
        
        # 2. الرافعة والسيولة
        if curr['long_term_debt'] <= prev['long_term_debt']: score += 1
        
        cur_ratio_curr = curr['current_assets'] / curr['current_liabilities'] if curr['current_liabilities'] else 0
        cur_ratio_prev = prev['current_assets'] / prev['current_liabilities'] if prev['current_liabilities'] else 0
        if cur_ratio_curr > cur_ratio_prev: score += 1
        
        # 3. الكفاءة (تقريبي باستخدام الإيرادات)
        turnover_curr = curr['revenue'] / curr['total_assets'] if curr['total_assets'] else 0
        turnover_prev = prev['revenue'] / prev['total_assets'] if prev['total_assets'] else 0
        if turnover_curr > turnover_prev: score += 1
        
        # النقاط المتبقية (هامش الربح، الأسهم) - نعطي نقطة افتراضية للتبسيط
        score += 1 
        
        metrics['Piotroski_Score'] = score
        
        # التقييم اللفظي
        if score >= 7: metrics['Financial_Health'] = "💪 صلبة (ممتازة)"
        elif score >= 5: metrics['Financial_Health'] = "👌 مستقرة (جيدة)"
        else: metrics['Financial_Health'] = "⚠️ هشة (تحتاج حذر)"
        
        metrics['Score'] = score
        metrics['Rating'] = metrics['Financial_Health']
        
        # الآراء النصية
        ops = []
        if curr['revenue'] > prev['revenue']: ops.append(f"نمو في الإيرادات ({((curr['revenue']-prev['revenue'])/prev['revenue']*100):.1f}%)")
        if curr['net_income'] < 0: ops.append("الشركة تسجل خسائر صافية")
        if curr['operating_cash_flow'] < 0: ops.append("تدفق نقدي تشغيلي سالب (خطر)")
        metrics['Opinions'] = " | ".join(ops)

    except Exception as e:
        print(f"Calc Error: {e}")
        
    return metrics

# ==============================================================
# 📊 واجهة المستخدم (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    # زر التحديث اليدوي
    c_btn, c_info = st.columns([1, 3])
    with c_btn:
        if st.button("🔄 جلب أحدث القوائم"):
            with st.spinner("جاري الاتصال بـ Yahoo وتحديث الأرشيف..."):
                ok, msg = sync_company_financials(symbol)
                if ok: st.success(msg); st.rerun()
                else: st.error(f"فشل: {msg}")
    
    # عرض البيانات من الأرشيف
    df = get_stored_financials_df(symbol)
    if df.empty:
        st.info("⚠️ لا توجد بيانات محفوظة. اضغط 'جلب أحدث القوائم' لبدء الأرشفة.")
        return

    # العرض التحليلي
    metrics = get_advanced_fundamental_ratios(symbol)
    
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("المتانة المالية (F-Score)", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
    with m2: 
        fv = metrics.get('Fair_Value_Graham')
        st.metric("قيمة جراهام العادلة", f"{fv:,.2f}" if fv else "-")
    with m3: st.write(metrics.get('Opinions', ''))

    st.markdown("---")
    
    # رسم بياني للنمو
    st.subheader("📈 التطور التاريخي (من الأرشيف)")
    df['Year'] = df['date'].dt.year.astype(str)
    
    fig = px.bar(df, x='Year', y=['revenue', 'net_income', 'operating_cash_flow'], 
                 barmode='group', title='الإيرادات vs الأرباح vs الكاش التشغيلي')
    st.plotly_chart(fig, use_container_width=True)
    
    # عرض الجدول التفصيلي (الأعمدة الجديدة)
    with st.expander("📂 جدول البيانات المالية المفصلة (Balance Sheet & Income)"):
        disp_cols = ['date', 'revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_liabilities', 'long_term_debt']
        st.dataframe(df[disp_cols].style.format("{:,.0f}"))

# توافق مع الكود القديم
def get_thesis(s): return {} 
def save_thesis(s, t, tg, r): pass
def save_financial_row(s, d, r): pass # لم نعد بحاجة لها، التحديث آلي
