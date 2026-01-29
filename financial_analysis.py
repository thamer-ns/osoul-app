import pandas as pd
import streamlit as st
import io
import yfinance as yf
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 📥 1. وحدة التخزين والمزامنة
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    try:
        def clean(val):
            try:
                if pd.isna(val) or val is None: return 0.0
                return float(val)
            except: return 0.0

        vals = {k: clean(data.get(k, 0)) for k in [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'total_equity', 'operating_cash_flow', 'current_assets', 
            'current_liabilities', 'long_term_debt'
        ]}

        if sum(vals.values()) == 0: return False

        query = """
            INSERT INTO "FinancialStatements" 
            (symbol, date, period_type, source, revenue, net_income, total_assets, total_liabilities, 
             total_equity, operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) 
            DO UPDATE SET 
                revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income,
                total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities,
                total_equity=EXCLUDED.total_equity, operating_cash_flow=EXCLUDED.operating_cash_flow,
                current_assets=EXCLUDED.current_assets, current_liabilities=EXCLUDED.current_liabilities,
                long_term_debt=EXCLUDED.long_term_debt, source=EXCLUDED.source;
        """
        execute_query(query, (
            symbol, date_str, period_type, source,
            vals['revenue'], vals['net_income'], vals['total_assets'], vals['total_liabilities'],
            vals['total_equity'], vals['operating_cash_flow'], vals['current_assets'],
            vals['current_liabilities'], vals['long_term_debt']
        ))
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False

def sync_auto_yahoo(symbol):
    try:
        ticker_sym = get_ticker_symbol(symbol)
        t = yf.Ticker(ticker_sym)
        count = 0
        
        def _process(df_fin, df_bs, df_cf, p_type):
            c = 0
            if df_fin.empty and df_bs.empty: return 0
            dates = sorted(list(set(df_fin.columns) | set(df_bs.columns) | set(df_cf.columns)), reverse=True)[:6]
            
            for d in dates:
                try:
                    d_str = d.strftime('%Y-%m-%d')
                    def get_val(df, key):
                        if d in df.columns and key in df.index: return df.loc[key, d]
                        return 0

                    data = {
                        'revenue': get_val(df_fin, 'Total Revenue'),
                        'net_income': get_val(df_fin, 'Net Income'),
                        'total_assets': get_val(df_bs, 'Total Assets'),
                        'total_liabilities': get_val(df_bs, 'Total Liabilities Net Minority Interest'),
                        'total_equity': get_val(df_bs, 'Total Equity Gross Minority Interest'),
                        'operating_cash_flow': get_val(df_cf, 'Operating Cash Flow'),
                        'current_assets': get_val(df_bs, 'Current Assets'),
                        'current_liabilities': get_val(df_bs, 'Current Liabilities'),
                        'long_term_debt': get_val(df_bs, 'Long Term Debt'),
                    }
                    if save_financial_record(symbol, d_str, data, p_type, 'Auto'): c += 1
                except: continue
            return c

        count += _process(t.financials, t.balance_sheet, t.cashflow, 'Annual')
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        
        if count == 0: return False, "لم يتم العثور على بيانات"
        return True, f"تم تحديث {count} سجلات"
    except Exception as e: return False, str(e)

def parse_pasted_text(txt):
    try:
        df = pd.read_csv(io.StringIO(txt), sep='\t')
        if df.shape[1] < 2: df = pd.read_csv(io.StringIO(txt), sep=r'\s+', engine='python')
        df.columns = df.columns.str.strip().str.lower()
        df = df.set_index(df.columns[0]).T.reset_index()
        results = []
        for _, row in df.iterrows():
            year = ''.join(filter(str.isdigit, str(row['index'])))
            if len(year) == 4:
                data = {}
                def find_val(keys):
                    for c in df.columns:
                        if any(k in str(c) for k in keys):
                            val = str(row[c]).replace(',', '').replace('(', '-').replace(')', '')
                            try: return float(val)
                            except: return 0.0
                    return 0.0
                
                data['revenue'] = find_val(['revenue', 'sales', 'إيرادات', 'مبيعات'])
                data['net_income'] = find_val(['net income', 'profit', 'ربح', 'صافي'])
                data['operating_cash_flow'] = find_val(['operating', 'تشغيلي', 'نقد'])
                data['total_assets'] = find_val(['total assets', 'مجموع الأصول', 'إجمالي الأصول'])
                data['total_equity'] = find_val(['equity', 'حقوق', 'ملكية'])
                results.append({'date': f"{year}-12-31", 'data': data})
        return results
    except: return []

# ==============================================================
# 🧠 2. وحدة التحليل (مع إصلاح الأرقام المركبة)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            required_cols = ['revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_equity', 'long_term_debt']
            for c in required_cols:
                if c not in df.columns: df[c] = 0.0
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    metrics = {"Fair_Value_Graham": 0.0, "Piotroski_Score": 0, "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""}
    
    df = get_stored_financials_df(symbol, 'Annual')
    if df.empty: df = get_stored_financials_df(symbol, 'Quarterly')
    if df.empty or len(df) < 1: return metrics
    
    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr
    
    try:
        # Piotroski F-Score
        score = 0
        if curr.get('net_income', 0) > 0: score += 1
        if curr.get('operating_cash_flow', 0) > 0: score += 1
        
        roa_c = curr.get('net_income', 0) / (curr.get('total_assets', 1) or 1)
        roa_p = prev.get('net_income', 0) / (prev.get('total_assets', 1) or 1)
        if roa_c > roa_p: score += 1
        
        if curr.get('operating_cash_flow', 0) > curr.get('net_income', 0): score += 1
        if curr.get('long_term_debt', 0) < prev.get('long_term_debt', 0): score += 1
        if curr.get('current_assets',0)/curr.get('current_liabilities',1) > prev.get('current_assets',0)/prev.get('current_liabilities',1): score += 1
        
        metrics['Piotroski_Score'] = min(score + 3, 9) # تقريب للواقع
        
        # ✅ إصلاح معادلة جراهام (منع الأرقام المركبة)
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps:
                product = 22.5 * eps * bvps
                # إذا كان الناتج سالب (خسائر)، القيمة العادلة تعتبر صفر أو غير قابلة للحساب
                if product > 0:
                    metrics['Fair_Value_Graham'] = product ** 0.5
                else:
                    metrics['Fair_Value_Graham'] = 0.0
        except: pass

        if score >= 5: metrics['Financial_Health'] = "جيد / مستقر"
        else: metrics['Financial_Health'] = "هش / يحتاج مراجعة"
        metrics['Score'] = metrics['Piotroski_Score']
        metrics['Rating'] = metrics['Financial_Health']

        ops = []
        if curr.get('net_income',0) > prev.get('net_income',0): ops.append("نمو في الأرباح")
        if curr.get('operating_cash_flow',0) < 0: ops.append("تدفق نقدي تشغيلي سالب ⚠️")
        metrics['Opinions'] = " | ".join(ops)

    except: pass
    return metrics

# ==============================================================
# 📊 3. واجهة المستخدم
# ==============================================================

def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة القوائم والبيانات"])
    
    with tab_dashboard:
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, label_visibility="collapsed")
        df = get_stored_financials_df(symbol, ptype)
        
        if df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 يرجى الانتقال لتبويب 'إدارة القوائم والبيانات' لجلب أو إدخال البيانات.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
            
            # عرض قيمة جراهام بشكل صحيح
            fv = metrics.get('Fair_Value_Graham', 0)
            c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv > 0 else "غير قابل للحساب (خسائر)")
            
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            st.markdown("---")
            
            try:
                df['Year'] = df['date'].dt.strftime('%Y-%m')
                cols_to_plot = [c for c in ['revenue', 'net_income', 'operating_cash_flow'] if c in df.columns and df[c].sum() != 0]
                if cols_to_plot:
                    fig = px.bar(df.sort_values('date'), x='Year', y=cols_to_plot, barmode='group', title="الأداء المالي التاريخي")
                    st.plotly_chart(fig, use_container_width=True)
            except: st.error("خطأ في الرسم")

            with st.expander("عرض الأرقام التفصيلية"):
                st.dataframe(df, use_container_width=True)

    with tab_data_mgmt:
        st.markdown("#### مصادر البيانات")
        src_t1, src_t2, src_t3 = st.tabs(["⚡ جلب آلي (Yahoo)", "📋 نسخ ولصق", "✍️ إدخال يدوي"])
        with src_t1:
            if st.button("بدء المزامنة الآلية"):
                with st.spinner("جاري الاتصال..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok: st.success(msg); st.rerun()
                    else: st.error(msg)
        with src_t2:
            txt = st.text_area("منطقة اللصق")
            if st.button("معالجة وحفظ"):
                res = parse_pasted_text(txt)
                if res:
                    for r in res: save_financial_record(symbol, r['date'], r['data'])
                    st.success("تم الحفظ"); st.rerun()
                else: st.error("تنسيق غير مدعوم")
