import pandas as pd
import streamlit as st
import io
import yfinance as yf
import plotly.express as px
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 📥 1. وحدة التخزين والمزامنة (Input & Storage)
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    """حفظ سجل مالي واحد في قاعدة البيانات"""
    try:
        # استخراج القيم بأمان
        vals = {k: float(data.get(k, 0) or 0) for k in [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'total_equity', 'operating_cash_flow', 'current_assets', 
            'current_liabilities', 'long_term_debt'
        ]}

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
    """جلب آلي (سنوي + ربعي)"""
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        count = 0
        
        def _process(df_fin, df_bs, df_cf, p_type):
            c = 0
            dates = sorted(list(set(df_fin.columns) | set(df_bs.columns) | set(df_cf.columns)), reverse=True)[:6]
            for d in dates:
                try:
                    d_str = d.strftime('%Y-%m-%d')
                    data = {
                        'revenue': df_fin[d].get('Total Revenue', 0) if d in df_fin else 0,
                        'net_income': df_fin[d].get('Net Income', 0) if d in df_fin else 0,
                        'total_assets': df_bs[d].get('Total Assets', 0) if d in df_bs else 0,
                        'total_liabilities': df_bs[d].get('Total Liabilities Net Minority Interest', 0) if d in df_bs else 0,
                        'total_equity': df_bs[d].get('Total Equity Gross Minority Interest', 0) if d in df_bs else 0,
                        'operating_cash_flow': df_cf[d].get('Operating Cash Flow', 0) if d in df_cf else 0,
                        'current_assets': df_bs[d].get('Current Assets', 0) if d in df_bs else 0,
                        'current_liabilities': df_bs[d].get('Current Liabilities', 0) if d in df_bs else 0,
                        'long_term_debt': df_bs[d].get('Long Term Debt', 0) if d in df_bs else 0,
                    }
                    if save_financial_record(symbol, d_str, data, p_type, 'Auto'): c+=1
                except: continue
            return c

        count += _process(t.financials, t.balance_sheet, t.cashflow, 'Annual')
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        
        return True, f"تم تحديث {count} سجلات (سنوي/ربعي)"
    except Exception as e: return False, str(e)

def parse_pasted_text(txt):
    """تحليل النسخ واللصق الذكي (الكود القديم المفضل لديك)"""
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
                data['total_assets'] = find_val(['assets', 'أصول'])
                data['total_equity'] = find_val(['equity', 'حقوق', 'ملكية'])
                
                results.append({'date': f"{year}-12-31", 'data': data})
        return results
    except: return []

# ==============================================================
# 🧠 2. وحدة التحليل (Analysis Engine)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            # ضمان وجود الأعمدة لمنع الأخطاء
            for c in ['operating_cash_flow', 'total_assets', 'total_equity']:
                if c not in df.columns: df[c] = 0.0
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    metrics = {"Fair_Value_Graham": None, "Piotroski_Score": 0, "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""}
    
    df = get_stored_financials_df(symbol, 'Annual')
    if df.empty: df = get_stored_financials_df(symbol, 'Quarterly')
    if df.empty or len(df) < 1: return metrics
    
    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr
    
    try:
        # 1. Piotroski F-Score (محسوب محلياً)
        score = 0
        if curr.get('net_income', 0) > 0: score += 1
        if curr.get('operating_cash_flow', 0) > 0: score += 1
        
        roa_c = curr.get('net_income', 0) / curr.get('total_assets', 1)
        roa_p = prev.get('net_income', 0) / prev.get('total_assets', 1)
        if roa_c > roa_p: score += 1
        
        if curr.get('operating_cash_flow', 0) > curr.get('net_income', 0): score += 1
        
        metrics['Piotroski_Score'] = min(score + 3, 9) # +3 تعويض تقريبي عن البيانات الناقصة
        
        # 2. Graham (تقريبي)
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps: metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass

        if score >= 5: metrics['Financial_Health'] = "جيد / مستقر"
        else: metrics['Financial_Health'] = "يحتاج مراجعة"
        metrics['Score'] = metrics['Piotroski_Score']
        metrics['Rating'] = metrics['Financial_Health']

        # الملاحظات
        ops = []
        if curr.get('net_income',0) > prev.get('net_income',0): ops.append("نمو الربحية")
        if curr.get('operating_cash_flow',0) < 0: ops.append("كاش تشغيلي سالب")
        metrics['Opinions'] = " | ".join(ops)

    except: pass
    return metrics

# ==============================================================
# 📊 3. واجهة المستخدم (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    # أدوات التحكم
    st.markdown("### 💰 التحليل المالي (Data Warehouse)")
    t_control, t_view = st.tabs(["⚙️ إدارة البيانات (قديم/جديد)", "📊 لوحة المعلومات"])
    
    with t_control:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### ⚡ جلب آلي (جديد)")
            if st.button("تحديث من Yahoo (سنوي + ربعي)", key="sync_btn"):
                with st.spinner("جاري المزامنة..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok: st.success(msg); st.rerun()
                    else: st.error(msg)
        
        with c2:
            st.markdown("##### ✍️ إدخال يدوي / نسخ (قديم)")
            with st.expander("فتح نموذج الإدخال"):
                sub_t1, sub_t2 = st.tabs(["نسخ جدول", "يدوي"])
                with sub_t1:
                    txt = st.text_area("الصق الجدول هنا")
                    if st.button("حفظ المنسوخ"):
                        res = parse_pasted_text(txt)
                        if res:
                            for r in res: save_financial_record(symbol, r['date'], r['data'])
                            st.success("تم الحفظ"); st.rerun()
                with sub_t2:
                    with st.form("man_f"):
                        dy = st.number_input("السنة", 2020, 2030, 2024)
                        rev = st.number_input("الإيرادات")
                        net = st.number_input("صافي الربح")
                        ocf = st.number_input("الكاش التشغيلي")
                        if st.form_submit_button("حفظ"):
                            save_financial_record(symbol, f"{dy}-12-31", {'revenue':rev, 'net_income':net, 'operating_cash_flow':ocf})
                            st.success("تم"); st.rerun()

    with t_view:
        ptype = st.radio("نوع الفترة:", ["Annual", "Quarterly"], horizontal=True)
        df = get_stored_financials_df(symbol, ptype)
        
        if df.empty:
            st.info("لا توجد بيانات محفوظة. الرجاء استخدام تبويب 'إدارة البيانات' لجلبها أو إدخالها.")
        else:
            # بطاقات
            curr = df.iloc[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("الإيرادات", f"{curr.get('revenue',0)/1e6:,.1f}M")
            m2.metric("صافي الربح", f"{curr.get('net_income',0)/1e6:,.1f}M")
            m3.metric("الكاش التشغيلي", f"{curr.get('operating_cash_flow',0)/1e6:,.1f}M")
            
            st.markdown("---")
            
            # الرسم البياني (مع حماية ضد ValueError)
            df['Year'] = df['date'].dt.strftime('%Y-%m') if not df.empty else []
            plot_cols = ['revenue', 'net_income']
            if 'operating_cash_flow' in df.columns and df['operating_cash_flow'].sum() != 0: 
                plot_cols.append('operating_cash_flow')
            
            # التأكد من أن الأعمدة رقمية
            for c in plot_cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
            try:
                fig = px.bar(df.sort_values('date'), x='Year', y=plot_cols, barmode='group', title="الأداء المالي")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"لا يمكن الرسم حالياً: {e}")
            
            with st.expander("جدول البيانات"):
                st.dataframe(df)

# دوال مساعدة لضمان عمل باقي النظام
def get_fundamental_ratios(symbol): return get_advanced_fundamental_ratios(symbol)
def get_thesis(s): 
    try: df = fetch_table("InvestmentThesis"); return df[df['symbol'] == s].iloc[0] if not df.empty else None
    except: return None
def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price, recommendation=EXCLUDED.recommendation", (s,t,float(tg),r))
