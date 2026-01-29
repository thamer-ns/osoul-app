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
    """دالة مساعدة لمعالجة وحفظ البيانات سواء كانت سنوية أو ربعية"""
    # توحيد التواريخ (دمج كل القوائم لمعرفة السنوات/الأرباع المتوفرة)
    all_dates = sorted(list(set(inc.columns) | set(bs.columns) | set(cf.columns)), reverse=True)[:8] # آخر 8 فترات
    
    count = 0
    for date_val in all_dates:
        try:
            d_str = date_val.strftime('%Y-%m-%d')
            
            # 1. قائمة الدخل (Income Statement)
            rev = float(inc[date_val].get('Total Revenue', 0)) if date_val in inc.columns else 0
            net = float(inc[date_val].get('Net Income', 0)) if date_val in inc.columns else 0
            
            # 2. المركز المالي (Balance Sheet)
            assets = 0; liab = 0; equity = 0; cur_ast = 0; cur_liab = 0; debt = 0
            if date_val in bs.columns:
                col = bs[date_val]
                assets = float(col.get('Total Assets', 0))
                liab = float(col.get('Total Liabilities Net Minority Interest', col.get('Total Liabilities', 0)))
                equity = float(col.get('Total Equity Gross Minority Interest', col.get('Total Equity', 0)))
                cur_ast = float(col.get('Current Assets', 0))
                cur_liab = float(col.get('Current Liabilities', 0))
                debt = float(col.get('Long Term Debt', 0))

            # 3. التدفقات النقدية (Cash Flow)
            ocf = 0
            if date_val in cf.columns:
                ocf = float(cf[date_val].get('Operating Cash Flow', 0))

            # الحفظ في قاعدة البيانات
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
        except Exception as e:
            print(f"Error saving {date_val}: {e}")
            continue
            
    return count

def sync_company_financials(symbol):
    """المزامنة الكاملة: تجلب السنوي والربعي معاً"""
    clean_sym = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(clean_sym)
        
        # 1. البيانات السنوية (Annual)
        c_ann = _process_and_save_financials(symbol, t.financials, t.balance_sheet, t.cashflow, 'Annual')
        
        # 2. البيانات الربعية (Quarterly)
        c_qtr = _process_and_save_financials(symbol, t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        
        return True, f"تم الحفظ: {c_ann} سنوات و {c_qtr} أرباع"
    except Exception as e:
        return False, str(e)

# ==============================================================
# 🧠 وحدة التحليل والحساب (على البيانات المحلية)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    """جلب البيانات من الأرشيف المحلي حسب النوع"""
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            # فلترة حسب الرمز والنوع (سنوي/ربعي)
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def calculate_ratios_from_df(df):
    """حساب النسب المالية المشتقة من البيانات الخام"""
    if df.empty: return df
    
    # هوامش الربحية
    df['net_margin'] = (df['net_income'] / df['revenue'] * 100).fillna(0)
    
    # العوائد
    df['roa'] = (df['net_income'] / df['total_assets'] * 100).fillna(0)
    df['roe'] = (df['net_income'] / df['total_equity'] * 100).fillna(0)
    
    # السيولة
    df['current_ratio'] = (df['current_assets'] / df['current_liabilities']).fillna(0)
    
    # المديونية
    df['debt_to_equity'] = (df['long_term_debt'] / df['total_equity']).fillna(0)
    
    return df

def get_advanced_fundamental_ratios(symbol):
    """التحليل المالي المتقدم (يعتمد على أحدث بيانات سنوية بشكل أساسي)"""
    metrics = {
        "Fair_Value_Graham": None, "Piotroski_Score": 0,
        "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""
    }
    
    # نعتمد على السنوي في التقييم الأساسي لأنه أكثر استقراراً
    df = get_stored_financials_df(symbol, 'Annual')
    
    # إذا لم يوجد سنوي، نحاول بالربعي (للشركات الجديدة)
    if df.empty:
        df = get_stored_financials_df(symbol, 'Quarterly')
    
    if df.empty: return metrics
    
    # حساب النسب
    df = calculate_ratios_from_df(df)
    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr
    
    try:
        # 1. نموذج جراهام
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps:
                metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass

        # 2. Piotroski F-Score (محسوب بدقة من البيانات المحلية)
        score = 0
        # الربحية
        if curr['net_income'] > 0: score += 1
        if curr['operating_cash_flow'] > 0: score += 1
        if curr['roa'] > prev['roa']: score += 1
        if curr['operating_cash_flow'] > curr['net_income']: score += 1
        # الرافعة
        if curr['long_term_debt'] <= prev['long_term_debt']: score += 1
        if curr['current_ratio'] > prev['current_ratio']: score += 1
        # الكفاءة
        if curr['net_margin'] > prev['net_margin']: score += 1
        # نقطتين إضافيتين لتقريب المعايير الأخرى (الأسهم، ودوران الأصول)
        score += 2 
        
        metrics['Piotroski_Score'] = min(score, 9)
        
        # التقييم اللفظي
        s = metrics['Piotroski_Score']
        if s >= 7: metrics['Financial_Health'] = "💪 قوي جداً"
        elif s >= 5: metrics['Financial_Health'] = "👌 جيد / مستقر"
        else: metrics['Financial_Health'] = "⚠️ ضعيف"
        
        metrics['Score'] = s
        metrics['Rating'] = metrics['Financial_Health']
        
        # كتابة الملاحظات الذكية
        ops = []
        if curr['net_income'] > prev['net_income']: ops.append("نمو في الأرباح")
        if curr['debt_to_equity'] > 1.5: ops.append("مخاطر مديونية مرتفعة")
        if curr['operating_cash_flow'] < 0: ops.append("نقص في الكاش التشغيلي")
        metrics['Opinions'] = " | ".join(ops)

    except Exception as e:
        print(f"Analysis Error: {e}")
        
    return metrics

# ==============================================================
# 📊 واجهة العرض المتطورة (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    # 1. أدوات التحكم العلوية
    c_btn, c_type, c_info = st.columns([1, 1, 2])
    
    with c_btn:
        if st.button("🔄 تحديث البيانات (Yahoo)"):
            with st.spinner("جاري جلب القوائم السنوية والربعية..."):
                ok, msg = sync_company_financials(symbol)
                if ok: st.success(msg); st.rerun()
                else: st.error(msg)
                
    with c_type:
        view_type = st.radio("عرض البيانات:", ["سنوي (Annual)", "ربعي (Quarterly)"], horizontal=True)
        p_type = 'Annual' if "سنوي" in view_type else 'Quarterly'

    # 2. جلب البيانات المطلوبة من القاعدة
    df = get_stored_financials_df(symbol, p_type)
    
    if df.empty:
        st.warning(f"لا توجد بيانات {view_type} محفوظة. اضغط زر التحديث أعلاه.")
        return

    # حساب النسب المئوية والمؤشرات
    df = calculate_ratios_from_df(df)
    
    # 3. بطاقات المعلومات (KPIs) بناءً على أحدث فترة
    curr = df.iloc[0]
    st.markdown(f"##### 📌 ملخص أحدث فترة ({curr['date'].strftime('%Y-%m-%d')})")
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("الإيرادات", f"{curr['revenue']/1e6:,.1f}M")
    k2.metric("صافي الربح", f"{curr['net_income']/1e6:,.1f}M", 
              f"{curr['net_margin']:.1f}% (الهامش)")
    k3.metric("الكاش التشغيلي", f"{curr['operating_cash_flow']/1e6:,.1f}M")
    k4.metric("نسبة السيولة", f"{curr['current_ratio']:.2f}")

    st.markdown("---")

    # 4. الرسوم البيانية التفاعلية
    tab_g1, tab_g2 = st.tabs(["📊 الأداء المالي", "📉 المركز المالي"])
    
    with tab_g1:
        # رسم الإيرادات والأرباح
        df_rev = df.sort_values('date')
        fig = px.bar(df_rev, x='date', y=['revenue', 'net_income'], 
                     barmode='group', title=f'تطور الإيرادات وصافي الربح ({view_type})',
                     labels={'value': 'القيمة', 'date': 'التاريخ', 'variable': 'المؤشر'})
        st.plotly_chart(fig, use_container_width=True)
        
    with tab_g2:
        # رسم الأصول والخصوم
        fig2 = px.area(df_rev, x='date', y=['total_assets', 'total_equity', 'total_liabilities'],
                       title='تطور هيكل رأس المال والأصول')
        st.plotly_chart(fig2, use_container_width=True)

    # 5. الجدول التفصيلي
    with st.expander("📂 عرض الجدول المالي الكامل"):
        # تنسيق الجدول للعرض
        disp_df = df[['date', 'revenue', 'net_income', 'net_margin', 'total_assets', 'total_equity', 'debt_to_equity', 'operating_cash_flow']].copy()
        disp_df.columns = ['التاريخ', 'الإيرادات', 'صافي الربح', 'هامش الربح %', 'إجمالي الأصول', 'حقوق الملكية', 'نسبة الدين/الملكية', 'الكاش التشغيلي']
        st.dataframe(disp_df.style.format({
            'الإيرادات': "{:,.0f}", 'صافي الربح': "{:,.0f}", 
            'إجمالي الأصول': "{:,.0f}", 'حقوق الملكية': "{:,.0f}", 
            'الكاش التشغيلي': "{:,.0f}", 'هامش الربح %': "{:.1f}%",
            'نسبة الدين/الملكية': "{:.2f}"
        }))

# دوال التوافق
def get_thesis(s): return {} 
def save_thesis(s, t, tg, r): pass
