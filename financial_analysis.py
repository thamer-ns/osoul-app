import pandas as pd
import streamlit as st
import io
import yfinance as yf
import plotly.express as px
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 📥 وحدة الإدخال والحفظ (Input & Storage Engine)
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual'):
    """دالة مركزية لحفظ سجل مالي واحد في قاعدة البيانات"""
    try:
        # تجهيز القيم مع وضع أصفار للاحتياط
        vals = {
            'revenue': float(data.get('revenue', 0)),
            'net_income': float(data.get('net_income', 0)),
            'total_assets': float(data.get('total_assets', 0)),
            'total_liabilities': float(data.get('total_liabilities', 0)),
            'total_equity': float(data.get('total_equity', 0)),
            'operating_cash_flow': float(data.get('operating_cash_flow', 0)),
            'current_assets': float(data.get('current_assets', 0)),
            'current_liabilities': float(data.get('current_liabilities', 0)),
            'long_term_debt': float(data.get('long_term_debt', 0))
        }

        query = """
            INSERT INTO "FinancialStatements" 
            (symbol, date, period_type, revenue, net_income, total_assets, total_liabilities, 
             total_equity, operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) 
            DO UPDATE SET 
                revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income,
                total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities,
                total_equity=EXCLUDED.total_equity, operating_cash_flow=EXCLUDED.operating_cash_flow,
                current_assets=EXCLUDED.current_assets, current_liabilities=EXCLUDED.current_liabilities,
                long_term_debt=EXCLUDED.long_term_debt;
        """
        execute_query(query, (
            symbol, date_str, period_type, 
            vals['revenue'], vals['net_income'], vals['total_assets'], vals['total_liabilities'],
            vals['total_equity'], vals['operating_cash_flow'], vals['current_assets'],
            vals['current_liabilities'], vals['long_term_debt']
        ))
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False

def parse_pasted_text(txt):
    """تحليل النص المنسوخ من Excel/PDF وتحويله لأرقام"""
    try:
        # محاولة قراءة النص كجدول
        df = pd.read_csv(io.StringIO(txt), sep='\t')
        if df.shape[1] < 2: df = pd.read_csv(io.StringIO(txt), sep=r'\s+', engine='python')
        
        df.columns = df.columns.str.strip().str.lower()
        # قلب الجدول ليكون (السنة) هي المفتاح
        df = df.set_index(df.columns[0]).T.reset_index()
        
        results = []
        for _, row in df.iterrows():
            # استخراج السنة
            year = ''.join(filter(str.isdigit, str(row['index'])))
            if len(year) == 4:
                data = {}
                # دالة بحث ذكية عن المصطلحات
                def find_val(keywords):
                    for c in df.columns:
                        if any(k in str(c) for k in keywords):
                            val = str(row[c]).replace(',', '').replace('(', '-').replace(')', '')
                            try: return float(val)
                            except: return 0.0
                    return 0.0
                
                data['revenue'] = find_val(['revenue', 'sales', 'إيرادات', 'مبيعات'])
                data['net_income'] = find_val(['net income', 'profit', 'ربح', 'صافي'])
                data['total_assets'] = find_val(['total assets', 'مجموع الأصول', 'إجمالي الأصول'])
                data['total_equity'] = find_val(['equity', 'حقوق الملكية', 'المساهمين'])
                data['operating_cash_flow'] = find_val(['operating cash', 'تشغيلي', 'نقد'])
                
                results.append({'date': f"{year}-12-31", 'data': data})
        return results
    except: return []

def sync_auto_yahoo(symbol):
    """الجلب الآلي من Yahoo"""
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        # جلب القوائم السنوية فقط كمثال (يمكن توسيعها للربعي)
        dates = t.financials.columns
        count = 0
        for d in dates:
            data = {
                'revenue': t.financials.loc['Total Revenue', d] if 'Total Revenue' in t.financials.index else 0,
                'net_income': t.financials.loc['Net Income', d] if 'Net Income' in t.financials.index else 0,
                'total_assets': t.balance_sheet.loc['Total Assets', d] if 'Total Assets' in t.balance_sheet.index else 0,
                'total_liabilities': t.balance_sheet.loc['Total Liabilities Net Minority Interest', d] if 'Total Liabilities Net Minority Interest' in t.balance_sheet.index else 0,
                'total_equity': t.balance_sheet.loc['Total Equity Gross Minority Interest', d] if 'Total Equity Gross Minority Interest' in t.balance_sheet.index else 0,
                'operating_cash_flow': t.cashflow.loc['Operating Cash Flow', d] if 'Operating Cash Flow' in t.cashflow.index else 0,
                'current_assets': t.balance_sheet.loc['Current Assets', d] if 'Current Assets' in t.balance_sheet.index else 0,
                'long_term_debt': t.balance_sheet.loc['Long Term Debt', d] if 'Long Term Debt' in t.balance_sheet.index else 0
            }
            if save_financial_record(symbol, d.strftime('%Y-%m-%d'), data, 'Annual'):
                count += 1
        return True, f"تم جلب وحفظ {count} سنوات"
    except Exception as e: return False, str(e)

# ==============================================================
# 🧠 وحدة التحليل (تقرأ من قاعدة البيانات حصراً)
# ==============================================================

def get_db_financials(symbol):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            df = df[df['symbol'] == symbol].copy()
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    metrics = {"Fair_Value_Graham": None, "Piotroski_Score": 0, "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""}
    
    # 1. القراءة من الأرشيف المحلي
    df = get_db_financials(symbol)
    if df.empty: return metrics
    
    # نأخذ أحدث سجل سنوي (أو ربعي إن لم يوجد سنوي)
    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr
    
    try:
        # --- التحليل ---
        # 1. Piotroski F-Score (محسوب محلياً)
        score = 0
        # ربحية
        if curr['net_income'] > 0: score += 1
        if curr['operating_cash_flow'] > 0: score += 1
        
        roa = curr['net_income'] / curr['total_assets'] if curr['total_assets'] else 0
        roa_prev = prev['net_income'] / prev['total_assets'] if prev['total_assets'] else 0
        if roa > roa_prev: score += 1
        
        if curr['operating_cash_flow'] > curr['net_income']: score += 1
        
        # كفاءة ورافعة
        if curr['long_term_debt'] <= prev['long_term_debt']: score += 1
        
        metrics['Piotroski_Score'] = min(score + 2, 9) # +2 تعويض عن البيانات الناقصة
        
        # 2. Graham Value
        # نحاول استخدام عدد الأسهم التقريبي لحساب حصة السهم
        # المعادلة المبسطة: جذر(22.5 * ربح السهم * القيمة الدفترية)
        # بما أننا لا نملك عدد الأسهم في قاعدة البيانات بدقة، سنستعين بـ Yahoo لجلب (Shares Outstanding) فقط لمرة واحدة
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            shares = t.info.get('sharesOutstanding')
            if shares:
                eps = curr['net_income'] / shares
                bvps = curr['total_equity'] / shares
                if eps > 0 and bvps > 0:
                    metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass

        # التقييم النهائي
        s = metrics['Piotroski_Score']
        if s >= 7: metrics['Financial_Health'] = "💪 صلبة (ممتازة)"
        elif s >= 5: metrics['Financial_Health'] = "👌 جيدة"
        else: metrics['Financial_Health'] = "⚠️ ضعيفة"
        metrics['Rating'] = metrics['Financial_Health']
        
        # كتابة الملاحظات
        ops = []
        if curr['net_income'] > prev['net_income']: ops.append("نمو في صافي الربح")
        if curr['operating_cash_flow'] < 0: ops.append("التدفق التشغيلي سالب (خطر)")
        metrics['Opinions'] = " | ".join(ops)

    except: pass
    return metrics

# ==============================================================
# 📊 واجهة المستخدم الموحدة (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    st.markdown("### 💰 الإدارة المالية والتحليل")
    
    # 1. عرض التحليل (يقرأ من المخزن)
    metrics = get_advanced_fundamental_ratios(symbol)
    c1, c2, c3 = st.columns(3)
    c1.metric("المتانة (F-Score)", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
    fv = metrics.get('Fair_Value_Graham')
    c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv else "غير متاح")
    c3.info(metrics.get('Opinions', 'لا توجد بيانات كافية للتحليل'))
    
    st.markdown("---")
    
    # 2. عرض البيانات التاريخية
    df = get_db_financials(symbol)
    if not df.empty:
        df['Year'] = df['date'].dt.strftime('%Y')
        fig = px.bar(df, x='Year', y=['revenue', 'net_income', 'operating_cash_flow'], 
                     barmode='group', title="الأداء المالي المحفوظ")
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("عرض الجدول التفصيلي"):
            st.dataframe(df.style.format("{:,.0f}"))
    else:
        st.warning("⚠️ لا توجد بيانات محفوظة لهذا السهم. استخدم أدوات الإدخال أدناه.")

    st.markdown("---")
    
    # 3. أدوات الإدخال (3 طرق)
    with st.expander("📥 إضافة / تحديث البيانات المالية (3 طرق)", expanded=False):
        tab1, tab2, tab3 = st.tabs(["⚡ سحب آلي", "📋 نسخ ولصق", "✍️ إدخال يدوي"])
        
        # أ: سحب آلي
        with tab1:
            if st.button("جلب من Yahoo Finance وحفظ في النظام"):
                with st.spinner("جاري العمل..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok: st.success(msg); st.rerun()
                    else: st.error(msg)
        
        # ب: نسخ ولصق
        with tab2:
            st.write("انسخ الجدول من ملف Excel أو PDF والصقه هنا:")
            txt = st.text_area("منطقة اللصق")
            if st.button("معالجة وحفظ"):
                res = parse_pasted_text(txt)
                if res:
                    cnt = 0
                    for r in res:
                        if save_financial_record(symbol, r['date'], r['data']): cnt+=1
                    st.success(f"تم حفظ {cnt} سجلات")
                    st.rerun()
                else: st.error("لم يتم التعرف على البيانات")
                
        # ج: إدخال يدوي
        with tab3:
            with st.form("manual_entry"):
                col1, col2 = st.columns(2)
                f_date = col1.date_input("تاريخ القوائم")
                f_rev = col2.number_input("الإيرادات", step=1000.0)
                f_net = col1.number_input("صافي الربح", step=1000.0)
                f_ast = col2.number_input("إجمالي الأصول", step=1000.0)
                f_eq = col1.number_input("حقوق الملكية", step=1000.0)
                f_ocf = col2.number_input("الكاش التشغيلي", step=1000.0)
                
                if st.form_submit_button("حفظ السجل"):
                    data = {
                        'revenue': f_rev, 'net_income': f_net, 
                        'total_assets': f_ast, 'total_equity': f_eq, 
                        'operating_cash_flow': f_ocf
                    }
                    if save_financial_record(symbol, str(f_date), data):
                        st.success("تم الحفظ")
                        st.rerun()

# دوال مساعدة لضمان عمل باقي النظام
def get_fundamental_ratios(symbol): return get_advanced_fundamental_ratios(symbol)
def get_thesis(s): 
    try: df = fetch_table("InvestmentThesis"); return df[df['symbol'] == s].iloc[0] if not df.empty else None
    except: return None
def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price, recommendation=EXCLUDED.recommendation", (s,t,float(tg),r))
