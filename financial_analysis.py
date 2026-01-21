import pandas as pd
import streamlit as st
import plotly.express as px
import io
from database import execute_query, get_db
from market_data import fetch_price_from_google, get_ticker_symbol

# === أدوات مساعدة ===
def debug_msg(msg):
    st.toast(msg)

# === 1. جلب مؤشرات أساسية (بديل Yahoo) ===
@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Score": 0, 
        "Rating": "تحليل يدوي", "Opinions": []
    }
    
    # السعر المباشر من Google Finance
    price = fetch_price_from_google(symbol)
    metrics["Current_Price"] = price
    
    if price == 0:
        metrics["Opinions"].append("تعذر جلب السعر المباشر من Google")
    else:
        # محاولة حساب P/E إذا توفرت بيانات سابقة
        try:
            df = get_stored_financials(symbol)
            if not df.empty:
                latest = df.sort_values('date').iloc[-1]
                metrics["Opinions"].append(f"آخر بيانات مالية: {latest['year']}")
        except: pass

    metrics["Opinions"].append("البيانات تعتمد على الإدخال اليدوي أو النسخ من أرقام")
    return metrics

# === 2. دالة النسخ الذكي (Argaam Parser) ===
def parse_pasted_text(raw_text):
    try:
        # محاولة قراءة النص كـ Tab Separated
        df = pd.read_csv(io.StringIO(raw_text), sep='\t')
        if len(df.columns) <= 1:
             df = pd.read_csv(io.StringIO(raw_text), sep=r'\s+', engine='python')

        df.columns = df.columns.str.strip().str.lower()
        
        # قلب الجدول (لأن أرقام تضع السنوات في الأعمدة)
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

# === 3. واجهة المستخدم ===
def render_financial_dashboard_ui(symbol):
    # أدوات الصيانة
    with st.expander("🛠️ أدوات الصيانة"):
        if st.button("إعادة تهيئة جدول القوائم المالية"):
            execute_query("DROP TABLE IF EXISTS FinancialStatements;")
            from database import init_db
            init_db()
            st.success("تم إعادة تهيئة الجدول بنجاح.")

    # منطقة الاستيراد
    st.markdown("### 📥 استيراد القوائم المالية")
    st.info(f"إدارة البيانات المالية لسهم: {get_ticker_symbol(symbol)}")
    
    tabs = st.tabs(["📋 نسخ من (أرقام/تداول)", "📂 ملف Excel/CSV", "✍️ إدخال يدوي"])
    
    with tabs[0]:
        st.markdown("1. اذهب لموقع **أرقام** أو **تداول**.\n2. انسخ جدول القوائم المالية (شامل العناوين والسنوات).\n3. ألصقه هنا:")
        pasted = st.text_area("مساحة اللصق", height=150, placeholder="الإيرادات    2023    2022\n1000       500     ...")
        if pasted and st.button("⚡ معالجة وحفظ البيانات"):
            data = parse_pasted_text(pasted)
            if data:
                c = 0
                for row in data:
                    save_financial_row(symbol, f"{row['year']}-12-31", row, "Argaam_Paste")
                    c += 1
                st.success(f"تم بنجاح حفظ بيانات {c} سنوات!")
                st.rerun()
            else: st.error("لم يتم التعرف على البيانات. تأكد من نسخ الجدول بشكل صحيح.")

    with tabs[1]:
        f = st.file_uploader("رفع ملف", type=['csv', 'xlsx'])
        if f: st.warning("تأكد من أن أسماء الأعمدة بالإنجليزية (year, revenue, net_income).")

    with tabs[2]:
        with st.form("manual"):
            c1, c2, c3 = st.columns(3)
            y = c1.number_input("السنة", value=2024, step=1)
            rev = c2.number_input("الإيرادات")
            net = c3.number_input("صافي الربح")
            if st.form_submit_button("💾 حفظ"):
                save_financial_row(symbol, f"{y}-12-31", {'revenue':rev, 'net_income':net}, "Manual")
                st.success("تم الحفظ")
                st.rerun()

    # عرض البيانات والرسوم
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
        st.warning("لا توجد بيانات مالية محفوظة. استخدم أدوات الاستيراد أعلاه.")

# === دوال قاعدة البيانات ===
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

# === دوال الأطروحة الاستثمارية ===
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
