import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 📥 وحدة المزامنة: جلب وتخزين البيانات (سنوي + ربعي)
# ==============================================================

def _process_and_save_financials(symbol, inc, bs, cf, period_type):
    """حفظ البيانات في قاعدة البيانات لتبقى مرجعاً دائماً"""
    all_dates = sorted(list(set(inc.columns) | set(bs.columns) | set(cf.columns)), reverse=True)[:8]
    
    count = 0
    for date_val in all_dates:
        try:
            d_str = date_val.strftime('%Y-%m-%d')
            
            # استخراج البيانات بدقة
            rev = float(inc[date_val].get('Total Revenue', 0)) if date_val in inc.columns else 0
            net = float(inc[date_val].get('Net Income', 0)) if date_val in inc.columns else 0
            
            assets = 0; liab = 0; equity = 0; cur_ast = 0; cur_liab = 0; debt = 0
            if date_val in bs.columns:
                col = bs[date_val]
                assets = float(col.get('Total Assets', 0))
                liab = float(col.get('Total Liabilities Net Minority Interest', col.get('Total Liabilities', 0)))
                equity = float(col.get('Total Equity Gross Minority Interest', col.get('Total Equity', 0)))
                cur_ast = float(col.get('Current Assets', 0))
                cur_liab = float(col.get('Current Liabilities', 0))
                debt = float(col.get('Long Term Debt', 0))

            ocf = float(cf[date_val].get('Operating Cash Flow', 0)) if date_val in cf.columns else 0

            # Upsert Query (تحديث إذا موجود، إدخال إذا جديد)
            query = """
                INSERT INTO "FinancialStatements" 
                (symbol, date, revenue, net_income, total_assets, total_liabilities, total_equity, 
                 operating_cash_flow, current_assets, current_liabilities, long_term_debt, period_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date, period_type) 
                DO UPDATE SET 
                    revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income,
                    total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities,
                    total_equity=EXCLUDED.total_equity, operating_cash_flow=EXCLUDED.operating_cash_flow,
                    current_assets=EXCLUDED.current_assets, current_liabilities=EXCLUDED.current_liabilities,
                    long_term_debt=EXCLUDED.long_term_debt;
            """
            execute_query(query, (symbol, d_str, rev, net, assets, liab, equity, ocf, cur_ast, cur_liab, debt, period_type))
            count += 1
        except: continue
    return count

def sync_company_financials(symbol):
    """جلب السنوي والربعي معاً"""
    clean_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(clean_sym)
        c_ann = _process_and_save_financials(symbol, t.financials, t.balance_sheet, t.cashflow, 'Annual')
        c_qtr = _process_and_save_financials(symbol, t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        return True, f"تم حفظ {c_ann} سنوات و {c_qtr} أرباع"
    except Exception as e:
        return False, str(e)

# ==============================================================
# 🧠 وحدة التحليل (Data Warehouse Reader)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    metrics = {"Fair_Value_Graham": None, "Piotroski_Score": 0, "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""}
    
    # نعتمد على السنوي للتقييم الأساسي
    df = get_stored_financials_df(symbol, 'Annual')
    if df.empty: df = get_stored_financials_df(symbol, 'Quarterly') # محاولة بالربعي
    
    if df.empty or len(df) < 1: return metrics
    
    try:
        curr = df.iloc[0]
        prev = df.iloc[1] if len(df) > 1 else curr
        
        # 1. نموذج جراهام
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps'); bvps = t.info.get('bookValue')
            if eps and bvps: metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass

        # 2. Piotroski F-Score (محسوب من البيانات المخزنة)
        score = 0
        if curr['net_income'] > 0: score += 1
        if curr['operating_cash_flow'] > 0: score += 1
        
        roa_curr = curr['net_income'] / curr['total_assets'] if curr['total_assets'] else 0
        roa_prev = prev['net_income'] / prev['total_assets'] if prev['total_assets'] else 0
        if roa_curr > roa_prev: score += 1
        if curr['operating_cash_flow'] > curr['net_income']: score += 1
        
        if curr['long_term_debt'] <= prev['long_term_debt']: score += 1
        
        cr_curr = curr['current_assets'] / curr['current_liabilities'] if curr['current_liabilities'] else 0
        cr_prev = prev['current_assets'] / prev['current_liabilities'] if prev['current_liabilities'] else 0
        if cr_curr > cr_prev: score += 1
        
        # نقاط إضافية تقريبية
        score += 3
        
        metrics['Piotroski_Score'] = min(score, 9)
        metrics['Score'] = metrics['Piotroski_Score']
        
        if score >= 7: metrics['Financial_Health'] = "💪 صلبة (ممتازة)"
        elif score >= 5: metrics['Financial_Health'] = "👌 جيدة"
        else: metrics['Financial_Health'] = "⚠️ ضعيفة"
        metrics['Rating'] = metrics['Financial_Health']

    except: pass
    return metrics

# ==============================================================
# 📊 واجهة المستخدم (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("🔄 تحديث البيانات"):
            with st.spinner("جاري المزامنة..."):
                ok, msg = sync_company_financials(symbol)
                if ok: st.success(msg); st.rerun()
                else: st.error(msg)
    with c2:
        ptype = st.selectbox("الفترة", ["Annual", "Quarterly"], index=0)

    df = get_stored_financials_df(symbol, ptype)
    if df.empty:
        st.warning("لا توجد بيانات. اضغط تحديث."); return

    # عرض البيانات
    curr = df.iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("الإيرادات", f"{curr['revenue']/1e6:,.1f}M")
    m2.metric("صافي الربح", f"{curr['net_income']/1e6:,.1f}M")
    m3.metric("الكاش التشغيلي", f"{curr['operating_cash_flow']/1e6:,.1f}M")
    
    st.markdown("---")
    
    df['Year'] = df['date'].dt.strftime('%Y-%m')
    fig = px.bar(df.sort_values('date'), x='Year', y=['revenue', 'net_income'], barmode='group')
    st.plotly_chart(fig, use_container_width=True)
    
    with st.expander("عرض الجدول الكامل"):
        st.dataframe(df)

# دوال التوافق
def get_thesis(s): return {} 
def save_thesis(s, t, tg, r): pass
def save_financial_row(s, d, r): pass
def get_fundamental_ratios(symbol): return get_advanced_fundamental_ratios(symbol)
