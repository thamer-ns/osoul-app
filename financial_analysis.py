import pandas as pd
import streamlit as st
import io
import yfinance as yf
import plotly.express as px
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 🏗️ وحدة إدارة البيانات (Backend Logic)
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    """حفظ سجل مالي في قاعدة البيانات"""
    try:
        # تنظيف القيم (تحويل None إلى 0.0)
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
    """جلب آلي من Yahoo"""
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        count = 0
        
        def _process(df_fin, df_bs, df_cf, p_type):
            c = 0
            # نأخذ التقاطع بين تواريخ القوائم المتاحة
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
        return True, f"تم تحديث {count} سجلات"
    except Exception as e: return False, str(e)

def parse_pasted_text(txt):
    """معالج النصوص المنسوخة (Excel/PDF)"""
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
                
                data['revenue'] = find_val(['revenue', 'sales', 'إيرادات', 'مبيعات', 'دخل'])
                data['net_income'] = find_val(['net income', 'profit', 'ربح', 'صافي'])
                data['operating_cash_flow'] = find_val(['operating', 'تشغيلي', 'نقد'])
                data['total_assets'] = find_val(['total assets', 'مجموع الأصول', 'إجمالي الأصول'])
                data['total_equity'] = find_val(['equity', 'حقوق', 'ملكية'])
                
                results.append({'date': f"{year}-12-31", 'data': data})
        return results
    except: return []

# ==============================================================
# 🧠 وحدة التحليل (Analysis Logic)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            # ضمان وجود الأعمدة لمنع ValueError
            required_cols = ['revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_equity', 'long_term_debt']
            for c in required_cols:
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
        # Piotroski F-Score (محلي)
        score = 0
        if curr.get('net_income', 0) > 0: score += 1
        if curr.get('operating_cash_flow', 0) > 0: score += 1
        
        roa_c = curr.get('net_income', 0) / (curr.get('total_assets', 1) or 1)
        roa_p = prev.get('net_income', 0) / (prev.get('total_assets', 1) or 1)
        if roa_c > roa_p: score += 1
        
        if curr.get('operating_cash_flow', 0) > curr.get('net_income', 0): score += 1
        
        metrics['Piotroski_Score'] = min(score + 4, 9) # تقريب
        
        # Graham
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps: metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass

        if score >= 5: metrics['Financial_Health'] = "جيد / مستقر"
        else: metrics['Financial_Health'] = "هش / يحتاج مراجعة"
        metrics['Score'] = metrics['Piotroski_Score']
        metrics['Rating'] = metrics['Financial_Health']

        ops = []
        if curr.get('net_income',0) > prev.get('net_income',0): ops.append("نمو في الأرباح")
        if curr.get('operating_cash_flow',0) < 0: ops.append("كاش تشغيلي سالب")
        metrics['Opinions'] = " | ".join(ops)

    except: pass
    return metrics

# ==============================================================
# 📊 واجهة المستخدم (UI Layer)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    # فصلنا التبويبات لتكون واضحة
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة القوائم والبيانات"])
    
    # --------------------------
    # 1. تبويب التحليل (المخرجات)
    # --------------------------
    with tab_dashboard:
        # اختيار الفترة للتحليل
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, label_visibility="collapsed")
        df = get_stored_financials_df(symbol, ptype)
        
        if df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 يرجى الانتقال لتبويب 'إدارة القوائم والبيانات' لجلب أو إدخال البيانات.")
        else:
            # التحليل الذكي
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
            fv = metrics.get('Fair_Value_Graham')
            c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv else "غير متاح")
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            
            st.markdown("---")
            
            # الرسوم البيانية (محمية من الأخطاء)
            try:
                df['Year'] = df['date'].dt.strftime('%Y-%m')
                # نختار فقط الأعمدة التي تحتوي على بيانات غير صفرية
                cols_to_plot = []
                for col in ['revenue', 'net_income', 'operating_cash_flow']:
                    if col in df.columns and df[col].sum() != 0:
                        cols_to_plot.append(col)
                
                if cols_to_plot:
                    fig = px.bar(df.sort_values('date'), x='Year', y=cols_to_plot, barmode='group', title="الأداء المالي التاريخي")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("البيانات المالية موجودة لكنها أصفار، لا يمكن الرسم.")
            except Exception as e:
                st.error(f"حدث خطأ أثناء الرسم: {e}")

            with st.expander("عرض الأرقام التفصيلية (الجدول)"):
                st.dataframe(df.style.format("{:,.0f}"))

    # --------------------------
    # 2. تبويب الإدارة (المدخلات)
    # --------------------------
    with tab_data_mgmt:
        st.markdown("#### مصادر البيانات")
        src_t1, src_t2, src_t3 = st.tabs(["⚡ جلب آلي (Yahoo)", "📋 نسخ ولصق (Excel)", "✍️ إدخال يدوي"])
        
        # أ. الجلب الآلي
        with src_t1:
            st.write("سيقوم النظام بجلب القوائم السنوية والربعية وحفظها.")
            if st.button("بدء المزامنة الآلية", key="btn_sync_yahoo"):
                with st.spinner("جاري الاتصال بالمخدمات..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok: st.success(msg); st.rerun()
                    else: st.error(f"فشل: {msg}")
        
        # ب. النسخ واللصق
        with src_t2:
            st.info("انسخ الجدول من ملف Excel أو PDF (تأكد أن السنة في الرأس أو الصف الأول).")
            txt = st.text_area("منطقة اللصق", height=150)
            if st.button("معالجة وحفظ النص", key="btn_paste_save"):
                res = parse_pasted_text(txt)
                if res:
                    saved_count = 0
                    for r in res:
                        if save_financial_record(symbol, r['date'], r['data']): saved_count += 1
                    st.success(f"تمت معالجة وحفظ {saved_count} سنوات.")
                    st.rerun()
                else: st.error("لم نتمكن من قراءة البيانات. تأكد من التنسيق.")
        
        # ج. الإدخال اليدوي
        with src_t3:
            with st.form("manual_data_form"):
                c_d1, c_d2 = st.columns(2)
                f_year = c_d1.number_input("السنة المالية", 2015, 2030, 2024)
                f_type = c_d2.selectbox("نوع القائمة", ["Annual", "Quarterly"])
                
                c_1, c_2 = st.columns(2)
                v_rev = c_1.number_input("الإيرادات (Revenue)", step=1000.0)
                v_net = c_2.number_input("صافي الربح (Net Income)", step=1000.0)
                v_ocf = c_1.number_input("الكاش التشغيلي", step=1000.0)
                v_ast = c_2.number_input("إجمالي الأصول", step=1000.0)
                
                if st.form_submit_button("حفظ السجل"):
                    date_str = f"{f_year}-12-31" if f_type == "Annual" else f"{f_year}-03-31" # تاريخ تقريبي للربع
                    data = {'revenue': v_rev, 'net_income': v_net, 'operating_cash_flow': v_ocf, 'total_assets': v_ast}
                    if save_financial_record(symbol, date_str, data, f_type, 'Manual'):
                        st.success("تم الحفظ بنجاح")
                        st.rerun()

# دوال مساعدة لربط باقي النظام
def get_fundamental_ratios(symbol): return get_advanced_fundamental_ratios(symbol)
def get_thesis(s): 
    try: df = fetch_table("InvestmentThesis"); return df[df['symbol'] == s].iloc[0] if not df.empty else None
    except: return None
def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price, recommendation=EXCLUDED.recommendation", (s,t,float(tg),r))
