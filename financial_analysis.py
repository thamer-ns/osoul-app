import pandas as pd
import streamlit as st
import plotly.express as px
import io
import pdfplumber  # مكتبة جديدة للتعامل مع PDF
from database import execute_query, get_db
from market_data import fetch_price_from_google, get_ticker_symbol

# === أدوات مساعدة ===
def debug_msg(msg):
    st.toast(msg)

# === 1. جلب مؤشرات أساسية ===
@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Score": 0, 
        "Rating": "تحليل يدوي", "Opinions": []
    }
    price = fetch_price_from_google(symbol)
    metrics["Current_Price"] = price
    if price == 0:
        metrics["Opinions"].append("تعذر جلب السعر المباشر من Google")
    else:
        try:
            df = get_stored_financials(symbol)
            if not df.empty:
                latest = df.sort_values('date').iloc[-1]
                metrics["Opinions"].append(f"آخر بيانات مالية: {latest['year']}")
        except: pass

    metrics["Opinions"].append("البيانات تعتمد على الإدخال اليدوي أو النسخ")
    return metrics

# === 2. دالة النسخ الذكي (Argaam Parser) ===
def parse_pasted_text(raw_text):
    # (نفس الكود السابق دون تغيير)
    try:
        df = pd.read_csv(io.StringIO(raw_text), sep='\t')
        if len(df.columns) <= 1:
             df = pd.read_csv(io.StringIO(raw_text), sep=r'\s+', engine='python')
        df.columns = df.columns.str.strip().str.lower()
        df_T = df.set_index(df.columns[0]).T
        df_T.reset_index(inplace=True)
        df_T.rename(columns={'index': 'year_raw'}, inplace=True)
        results = []
        for _, row in df_T.iterrows():
            year_str = str(row['year_raw'])
            year = ''.join(filter(str.isdigit, year_str))
            if len(year) == 4:
                def get_val(keywords):
                    for col in df_T.columns:
                        if any(k in str(col) for k in keywords):
                            val = str(row[col]).replace(',', '').replace('(', '-').replace(')', '')
                            try: return float(val)
                            except: continue
                    return 0.0
                data_row = {
                    'year': year,
                    'revenue': get_val(['إيرادات', 'مبيعات', 'Revenue']),
                    'net_income': get_val(['صافي', 'الربح', 'Net Income']),
                    'total_assets': get_val(['مجموع الأصول', 'Total Assets', 'الموجودات']),
                    'total_equity': get_val(['حقوق المساهمين', 'Equity', 'الملكية']),
                    'operating_cash_flow': get_val(['تشغيلي', 'Operating Cash'])
                }
                if data_row['revenue'] != 0 or data_row['net_income'] != 0:
                    results.append(data_row)
        return results
    except: return []

# === 3. دالة استخراج من PDF (جديد) ===
def extract_from_pdf(uploaded_file):
    """محاولة استخراج الجداول المالية من PDF"""
    results = []
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                # استخراج الجداول
                tables = page.extract_tables()
                for table in tables:
                    # تحويل الجدول إلى DataFrame للتنظيف
                    df = pd.DataFrame(table)
                    # هنا يجب وضع منطق ذكي للتعرف على الصفوف (مثل: صف يحتوي "الإيرادات")
                    # هذا تبسيط، حيث نفترض أن المستخدم سيرفع صفحة القوائم فقط
                    # يمكن تطوير هذا الجزء ليكون أكثر ذكاءً
                    pass
        # ملاحظة: استخراج PDF معقد جداً في العربية، لذا سنعتمد حالياً على 
        # مكتبة Camelot أو Tabula إذا أردنا دقة أعلى، لكن pdfplumber أسهل في التثبيت.
        # حالياً سأعيد قائمة فارغة لتنبيه المستخدم أن الخاصية تجريبية
        return [] 
    except Exception as e:
        st.error(f"خطأ في قراءة PDF: {e}")
        return []

# === 4. واجهة المستخدم ===
def render_financial_dashboard_ui(symbol):
    with st.expander("🛠️ أدوات الصيانة"):
        if st.button("إعادة تهيئة جدول القوائم المالية"):
            execute_query("DROP TABLE IF EXISTS FinancialStatements;")
            from database import init_db; init_db()
            st.success("تم إعادة تهيئة الجدول بنجاح.")

    st.markdown("### 📥 استيراد القوائم المالية")
    st.info(f"إدارة البيانات المالية لسهم: {get_ticker_symbol(symbol)}")
    
    # إضافة تبويب PDF
    tabs = st.tabs(["📋 نسخ (أرقام/تداول)", "📄 ملف PDF (تجريبي)", "📂 ملف Excel/CSV", "✍️ يدوي"])
    
    with tabs[0]:
        st.markdown("انسخ الجدول من موقع أرقام أو تداول وألصقه هنا:")
        pasted = st.text_area("مساحة اللصق", height=150)
        if pasted and st.button("⚡ معالجة النص"):
            data = parse_pasted_text(pasted)
            if data:
                c = 0
                for row in data:
                    save_financial_row(symbol, f"{row['year']}-12-31", row, "Argaam_Paste")
                    c += 1
                st.success(f"تم حفظ بيانات {c} سنوات!")
                st.rerun()
            else: st.error("لم يتم التعرف على البيانات.")

    with tabs[1]:
        st.markdown("**ميزة تجريبية:** ارفع ملف القوائم المالية (PDF)")
        pdf_file = st.file_uploader("رفع PDF", type=['pdf'])
        if pdf_file:
            st.info("جاري تحليل الملف... (يدعم الجداول الإنجليزية بشكل أفضل)")
            # يمكن تفعيل extract_from_pdf هنا عند تطوير المنطق الخاص بها
            st.warning("الاستخراج الآلي من PDF يتطلب مكتبات إضافية (Java/Tabula)، يفضل استخدام النسخ واللصق حالياً للدقة.")

    with tabs[2]:
        f = st.file_uploader("رفع ملف", type=['csv', 'xlsx'])
        if f: st.warning("تأكد من أسماء الأعمدة (year, revenue, net_income).")

    with tabs[3]:
        with st.form("manual"):
            c1, c2, c3 = st.columns(3)
            y = c1.number_input("السنة", value=2024, step=1)
            rev = c2.number_input("الإيرادات")
            net = c3.number_input("صافي الربح")
            if st.form_submit_button("💾 حفظ"):
                save_financial_row(symbol, f"{y}-12-31", {'revenue':rev, 'net_income':net}, "Manual")
                st.success("تم الحفظ"); st.rerun()

    # عرض البيانات والرسوم (نفس الكود السابق)
    df = get_stored_financials(symbol)
    if not df.empty:
        df['year'] = pd.to_datetime(df['date']).dt.year
        df = df.sort_values('year')
        st.markdown("---")
        c_chart, c_table = st.columns([2, 1])
        with c_chart:
            st.markdown("##### 📊 النمو المالي")
            if 'revenue' in df.columns and 'net_income' in df.columns:
                chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'], var_name='المؤشر', value_name='القيمة')
                chart_df['المؤشر'] = chart_df['المؤشر'].map({'revenue': 'الإيرادات', 'net_income': 'صافي الربح'})
                fig = px.bar(chart_df, x='year', y='القيمة', color='المؤشر', barmode='group', 
                             color_discrete_map={'الإيرادات': '#2962FF', 'صافي الربح': '#00C853'})
                fig.update_layout(paper_bgcolor="white", plot_bgcolor="white", font={'family': "Cairo"}, height=350)
                st.plotly_chart(fig, use_container_width=True)
        with c_table:
            st.markdown("##### 📑 الأرقام")
            st.dataframe(df[['year', 'revenue', 'net_income']].set_index('year'), use_container_width=True)
    else:
        st.warning("لا توجد بيانات مالية محفوظة.")

# === دوال قاعدة البيانات (نفس السابق) ===
def save_financial_row(symbol, date_str, row, source):
    def sf(val):
        try: return float(val)
        except: return 0.0
    query = """
        INSERT INTO FinancialStatements 
        (symbol, period_type, date, revenue, net_income, gross_profit, operating_income, total_assets, total_liabilities, total_equity, operating_cash_flow, free_cash_flow, eps, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, period_type, date) DO UPDATE SET
        revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income, 
        total_assets=EXCLUDED.total_assets, total_equity=EXCLUDED.total_equity,
        operating_cash_flow=EXCLUDED.operating_cash_flow;
    """
    vals = (
        symbol, 'Annual', date_str, 
        sf(row.get('revenue', 0)), sf(row.get('net_income', 0)), 0, 
        0, sf(row.get('total_assets', 0)), 
        0, sf(row.get('total_equity', 0)), 
        sf(row.get('operating_cash_flow', 0)), 0, 
        0, source
    )
    execute_query(query, vals)

def get_stored_financials(symbol):
    with get_db() as conn:
        if conn:
            try: return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol = %s ORDER BY date ASC", conn, params=(symbol,))
            except: pass
    return pd.DataFrame()

def save_thesis(symbol, text, target, rec):
    query = """
    INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation, last_updated)
    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON CONFLICT (symbol) DO UPDATE SET 
        thesis_text = EXCLUDED.thesis_text, 
        target_price = EXCLUDED.target_price, 
        recommendation = EXCLUDED.recommendation, 
        last_updated = CURRENT_TIMESTAMP;
    """
    execute_query(query, (symbol, text, target, rec))

def get_thesis(symbol):
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql("SELECT * FROM InvestmentThesis WHERE symbol = %s", conn, params=(symbol,))
                if not df.empty: return df.iloc[0]
            except: pass
    return None
