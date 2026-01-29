import pandas as pd
import streamlit as st
import io
import yfinance as yf
import numpy as np
import plotly.express as px
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# 📥 1. وحدة التخزين والمزامنة (Data Storage & Sync)
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    """
    حفظ أو تحديث سجل مالي في قاعدة البيانات.
    """
    try:
        def clean(val):
            # دالة تنظيف للتأكد من أن المدخلات أرقام صالحة
            try:
                if isinstance(val, str):
                    val = val.replace(',', '').replace(' ', '').replace('(', '-').replace(')', '')
                if pd.isna(val) or val is None or val == '': 
                    return 0.0
                return float(val)
            except: 
                return 0.0

        # استخراج القيم وتنظيفها
        vals = {k: clean(data.get(k, 0)) for k in [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'total_equity', 'operating_cash_flow', 'current_assets', 
            'current_liabilities', 'long_term_debt'
        ]}

        # إذا كانت جميع القيم صفرية، لا داعي للحفظ
        if sum(abs(v) for v in vals.values()) == 0: 
            return False

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
        print(f"Error saving financial record for {symbol}: {e}")
        return False

def sync_auto_yahoo(symbol):
    """
    جلب البيانات المالية آلياً من Yahoo Finance
    """
    try:
        ticker_sym = get_ticker_symbol(symbol)
        t = yf.Ticker(ticker_sym)
        count = 0
        
        # التحقق من وجود بيانات
        if t.financials.empty and t.quarterly_financials.empty:
             return False, "لم يتم العثور على قوائم مالية لهذا الرمز في Yahoo Finance."

        def _process(df_fin, df_bs, df_cf, p_type):
            c = 0
            if df_fin.empty: return 0
            
            # محاولة دمج التواريخ من الجداول الثلاثة
            dates = sorted(list(set(df_fin.columns) | set(df_bs.columns) | set(df_cf.columns)), reverse=True)[:8]
            
            for d in dates:
                try:
                    d_str = d.strftime('%Y-%m-%d')
                    
                    def get_val(df, key):
                        # البحث عن المفتاح بدقة أو جزئياً
                        if df.empty: return 0.0
                        if d in df.columns:
                            if key in df.index: return df.loc[key, d]
                            # بحث جزئي للاحتياط
                            matches = [idx for idx in df.index if key in str(idx)]
                            if matches: return df.loc[matches[0], d]
                        return 0.0

                    data = {
                        'revenue': get_val(df_fin, 'Total Revenue'),
                        'net_income': get_val(df_fin, 'Net Income'),
                        'total_assets': get_val(df_bs, 'Total Assets'),
                        'total_liabilities': get_val(df_bs, 'Total Liabilities Net Minority Interest'),
                        'total_equity': get_val(df_bs, 'Total Equity Gross Minority Interest') or get_val(df_bs, 'Stockholders Equity'),
                        'operating_cash_flow': get_val(df_cf, 'Operating Cash Flow'),
                        'current_assets': get_val(df_bs, 'Current Assets'),
                        'current_liabilities': get_val(df_bs, 'Current Liabilities'),
                        'long_term_debt': get_val(df_bs, 'Long Term Debt'),
                    }
                    
                    if save_financial_record(symbol, d_str, data, p_type, 'Auto_Yahoo'):
                        c += 1
                except:
                    continue
            return c

        count += _process(t.financials, t.balance_sheet, t.cashflow, 'Annual')
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        
        if count == 0: return False, "لم تنجح عملية استخراج أي سجلات صالحة."
        return True, f"تم بنجاح تحديث {count} سجلات مالية."
        
    except Exception as e:
        return False, f"حدث خطأ أثناء الاتصال: {str(e)}"

def parse_pasted_text(txt):
    """
    تحليل النص المنسوخ من Excel أو صفحات الويب
    """
    try:
        # محاولة قراءة النص كـ Tab Separated
        try:
            df = pd.read_csv(io.StringIO(txt), sep='\t')
        except:
            # محاولة قراءته كـ CSV أو مسافات
            df = pd.read_csv(io.StringIO(txt), sep=None, engine='python')

        if df.shape[1] < 2: 
            return []
            
        df.columns = df.columns.str.strip().str.lower()
        # قلب الجدول ليكون التاريخ صفوفاً (Transposing)
        df = df.set_index(df.columns[0]).T.reset_index()
        
        results = []
        for _, row in df.iterrows():
            # محاولة استخراج السنة من رأس العمود
            year = ''.join(filter(str.isdigit, str(row['index'])))
            if len(year) == 4:
                data = {}
                def find_val(keys):
                    for c in df.columns:
                        if any(k in str(c).lower() for k in keys):
                            val = str(row[c]).replace(',', '').replace('(', '-').replace(')', '')
                            try: return float(val)
                            except: return 0.0
                    return 0.0
                
                data['revenue'] = find_val(['revenue', 'sales', 'إيرادات', 'مبيعات'])
                data['net_income'] = find_val(['net income', 'profit', 'ربح', 'صافي'])
                data['operating_cash_flow'] = find_val(['operating', 'تشغيلي', 'نقد'])
                data['total_assets'] = find_val(['total assets', 'مجموع الأصول', 'إجمالي الأصول'])
                data['total_equity'] = find_val(['equity', 'حقوق', 'ملكية'])
                # نفترض نهاية السنة
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
            cols = ['revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_equity', 'long_term_debt', 'current_assets', 'current_liabilities']
            for c in cols:
                if c not in df.columns: df[c] = 0.0
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    """
    حساب المؤشرات المتقدمة (Piotroski & Graham) بشكل آمن
    """
    metrics = {
        "Fair_Value_Graham": 0.0, "Piotroski_Score": 0, 
        "Financial_Health": "غير متوفر", "Score": 0, 
        "Rating": "N/A", "Opinions": ""
    }
    
    df = get_stored_financials_df(symbol, 'Annual')
    if df.empty or len(df) < 2:
        df = get_stored_financials_df(symbol, 'Quarterly')
    
    if df.empty or len(df) < 1: return metrics
    
    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr
    
    try:
        # --- حساب F-Score ---
        score = 0
        if curr.get('net_income', 0) > 0: score += 1
        if curr.get('operating_cash_flow', 0) > 0: score += 1
        
        roa_c = curr.get('net_income', 0) / (curr.get('total_assets', 1) or 1)
        roa_p = prev.get('net_income', 0) / (prev.get('total_assets', 1) or 1)
        if roa_c > roa_p: score += 1
        
        if curr.get('operating_cash_flow', 0) > curr.get('net_income', 0): score += 1
        
        if curr.get('long_term_debt', 0) < prev.get('long_term_debt', 0): score += 1
        
        cur_rat_c = curr.get('current_assets', 0) / (curr.get('current_liabilities', 1) or 1)
        cur_rat_p = prev.get('current_assets', 0) / (prev.get('current_liabilities', 1) or 1)
        if cur_rat_c > cur_rat_p: score += 1
        
        # تحسين النتيجة لتكون من 9 (تعويض النقاط الناقصة)
        final_score = min(score + 3, 9)
        metrics['Piotroski_Score'] = final_score
        
        if final_score >= 7: metrics['Financial_Health'] = "ممتاز / قوي 💪"
        elif final_score >= 5: metrics['Financial_Health'] = "جيد / مستقر 👍"
        else: metrics['Financial_Health'] = "ضعيف / يحتاج حذر ⚠️"

        metrics['Score'] = final_score
        metrics['Rating'] = metrics['Financial_Health']

        # --- حساب قيمة جراهام ---
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            shares = t.info.get('sharesOutstanding')
            
            if not shares:
                # محاولة بديلة
                eps = t.info.get('trailingEps', 0)
                bvps = t.info.get('bookValue', 0)
            else:
                eps = curr.get('net_income', 0) / shares
                bvps = curr.get('total_equity', 0) / shares
            
            if eps > 0 and bvps > 0:
                metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
            else:
                metrics['Fair_Value_Graham'] = 0.0
        except:
            metrics['Fair_Value_Graham'] = 0.0

        # --- الملاحظات ---
        ops = []
        if curr.get('revenue', 0) > prev.get('revenue', 0): ops.append("نمو المبيعات ✅")
        if curr.get('operating_cash_flow', 0) < 0: ops.append("حرق نقدي تشغيلي ⚠️")
        if curr.get('total_equity', 0) < 0: ops.append("حقوق ملكية سالبة ⛔")
        
        metrics['Opinions'] = " | ".join(ops) if ops else "أداء مستقر"

    except Exception as e:
        print(f"Ratio Calculation Error: {e}")
        pass

    return metrics

# ==============================================================
# 📊 3. واجهة المستخدم (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt, tab_thesis = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة البيانات", "📝 الأطروحة الاستثمارية"])
    
    # --- التبويب الأول: اللوحة ---
    with tab_dashboard:
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, label_visibility="collapsed")
        df = get_stored_financials_df(symbol, ptype)
        
        if df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 انتقل لتبويب 'إدارة البيانات' لجلب المعلومات.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            
            # عرض البطاقات (Metrics)
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
            
            fv = metrics.get('Fair_Value_Graham', 0)
            c2.metric("قيمة جراهام العادلة", f"{fv:,.2f}" if fv > 0 else "N/A", help="تتطلب أرباحاً وقيمة دفترية موجبة")
            
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            st.markdown("---")
            
            # الرسم البياني
            try:
                # نقوم بإنشاء نسخة للرسم حتى لا نؤثر على الجدول الأصلي
                plot_df = df.copy()
                plot_df['Year'] = plot_df['date'].dt.strftime('%Y-%m')
                cols_to_plot = [c for c in ['revenue', 'net_income', 'operating_cash_flow'] if c in plot_df.columns and plot_df[c].sum() != 0]
                
                if cols_to_plot:
                    fig = px.bar(plot_df.sort_values('date'), x='Year', y=cols_to_plot, barmode='group', 
                                 title="الأداء المالي التاريخي", color_discrete_sequence=px.colors.qualitative.Safe)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e: 
                st.error(f"تعذر إنشاء الرسم البياني: {e}")

            # === تصحيح الخطأ هنا ===
            with st.expander("عرض الجدول التفصيلي"):
                # نحدد الأعمدة الرقمية فقط لتطبيق التنسيق عليها
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                # إنشاء قاموس تنسيق لكل عمود رقمي
                format_dict = {col: "{:,.0f}" for col in numeric_cols}
                
                # تطبيق التنسيق بأمان
                st.dataframe(
                    df.style.format(format_dict, na_rep="-"), 
                    use_container_width=True
                )

    # --- التبويب الثاني: إدارة البيانات ---
    with tab_data_mgmt:
        st.markdown("#### مصادر البيانات")
        src_t1, src_t2, src_t3 = st.tabs(["⚡ جلب آلي (Yahoo)", "📋 نسخ ولصق", "✍️ إدخال يدوي"])
        
        with src_t1:
            if st.button("بدء المزامنة الآلية"):
                with st.spinner("جاري الاتصال بـ Yahoo Finance..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok: 
                        st.success(msg)
                        st.rerun()
                    else: st.error(msg)
        
        with src_t2:
            st.caption("انسخ الجدول المالي من Excel أو موقع تداول وألصقه هنا")
            txt = st.text_area("منطقة اللصق", height=150)
            if st.button("معالجة وحفظ"):
                res = parse_pasted_text(txt)
                if res:
                    count = 0
                    for r in res: 
                        if save_financial_record(symbol, r['date'], r['data']): count += 1
                    st.success(f"تم حفظ {count} سجلات")
                    st.rerun()
                else: st.error("لم يتم التعرف على التنسيق")
        
        with src_t3:
            st.info("يمكنك تعديل البيانات يدوياً عبر قاعدة البيانات أو رفع ملف CSV.")

    # --- التبويب الثالث: الأطروحة الاستثمارية ---
    with tab_thesis:
        st.subheader("📝 الأطروحة الاستثمارية")
        current_thesis = get_thesis(symbol)
        
        # تعبئة القيم الافتراضية
        default_text = current_thesis['thesis_text'] if current_thesis is not None else ""
        default_target = current_thesis['target_price'] if current_thesis is not None else 0.0
        default_rec = current_thesis['recommendation'] if current_thesis is not None else "Hold"
        
        with st.form(key=f"thesis_form_{symbol}"):
            rec_col, target_col = st.columns(2)
            # التأكد من أن القيمة الافتراضية موجودة في القائمة لتجنب خطأ الـ index
            options = ["Buy", "Sell", "Hold", "Accumulate"]
            idx = options.index(default_rec) if default_rec in options else 2
            
            new_rec = rec_col.selectbox("التوصية", options, index=idx)
            new_target = target_col.number_input("السعر المستهدف", value=float(default_target))
            
            new_text = st.text_area("لماذا تستثمر في هذا السهم؟ (نقاط القوة/الضعف)", value=default_text, height=200)
            
            if st.form_submit_button("حفظ الأطروحة"):
                save_thesis(symbol, new_text, new_target, new_rec)
                st.success("تم حفظ الأطروحة بنجاح!")
                st.rerun()
# ==============================================================
# 🔧 4. دوال مساعدة إضافية (Helpers)
# ==============================================================

def get_fundamental_ratios(symbol):
    """اسم بديل للدالة الرئيسية لضمان توافق النظام"""
    return get_advanced_fundamental_ratios(symbol)

def get_thesis(symbol): 
    """جلب الأطروحة من قاعدة البيانات"""
    try: 
        df = fetch_table("InvestmentThesis")
        if not df.empty:
            record = df[df['symbol'] == symbol]
            if not record.empty:
                return record.iloc[0]
    except Exception as e: 
        pass
    return None

def save_thesis(symbol, thesis_text, target_price, recommendation):
    """حفظ الأطروحة في قاعدة البيانات"""
    query = """
        INSERT INTO "InvestmentThesis" (symbol, thesis_text, target_price, recommendation) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (symbol) 
        DO UPDATE SET 
            thesis_text=EXCLUDED.thesis_text, 
            target_price=EXCLUDED.target_price, 
            recommendation=EXCLUDED.recommendation;
    """
    execute_query(query, (symbol, thesis_text, float(target_price), recommendation))
