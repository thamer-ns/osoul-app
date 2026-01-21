import pandas as pd
import streamlit as st
import plotly.express as px
import io
import requests
from bs4 import BeautifulSoup
from database import execute_query, get_db
from market_data import fetch_price_from_google, get_ticker_symbol

# === أدوات مساعدة ===
def debug_msg(msg):
    st.toast(msg)

# === 1. جلب مؤشرات أساسية عبر البحث (بديل Yahoo) ===
@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    # القيم الافتراضية
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Score": 0, 
        "Rating": "تحليل يدوي", "Opinions": []
    }
    
    # 1. السعر المباشر من Google Finance
    price = fetch_price_from_google(symbol)
    metrics["Current_Price"] = price
    
    if price == 0:
        metrics["Opinions"].append("تعذر جلب السعر المباشر من Google")
        return metrics

    # بما أننا لغينا Yahoo، الحصول على P/E و EPS آلياً صعب جداً ومحمي
    # سنضيف ملاحظة للمستخدم للاعتماد على بيانات أرقام
    metrics["Opinions"].append("⚠️ تم إيقاف Yahoo. يرجى استخدام ميزة 'استيراد أرقام' أدناه للحصول على التحليل المالي الدقيق.")
    
    # يمكننا محاولة حساب P/E إذا توفرت بيانات في قاعدة البيانات
    try:
        df = get_stored_financials(symbol)
        if not df.empty:
            latest = df.sort_values('date').iloc[-1]
            # إذا توفر صافي الدخل وعدد الأسهم (نفترض عدد أسهم تقديري أو نطلبه)
            # سنقوم بحسابات تقريبية بناءً على آخر بيانات مدخلة يدوياً
            if latest['net_income'] > 0:
                metrics["Opinions"].append(f"آخر بيانات مالية مسجلة: {latest['year']}")
    except: pass

    return metrics

# === 2. دوال الاستيراد الذكي (أرقام / تداول) ===
# (نفس دالة النسخ الذكي السابقة لأنها ممتازة ولا تعتمد على Yahoo)
def parse_pasted_text(raw_text):
    try:
        df = pd.read_csv(io.StringIO(raw_text), sep='\t')
        if len(df.columns) <= 1:
             df = pd.read_csv(io.StringIO(raw_text), sep=r'\s+', engine='python')

        df.columns = df.columns.str.strip().str.lower()
        
        # محاولة التعامل مع هيكلية "أرقام" و "تداول"
        # أرقام: السنوات في الأعمدة
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
    # تنظيف الجدول
    with st.expander("🛠️ أدوات الصيانة"):
        if st.button("إعادة تهيئة الجدول"):
            execute_query("DROP TABLE IF EXISTS FinancialStatements;")
            from database import init_db
            init_db()
            st.success("تم.")

    # القسم الرئيسي: استيراد البيانات
    st.markdown("### 📥 استيراد البيانات المالية")
    st.info("نظراً لإيقاف Yahoo، هذا هو المصدر المعتمد لبياناتك.")
    
    tabs = st.tabs(["📋 نسخ من (أرقام/تداول)", "📂 ملف TradingView/Excel", "✍️ إدخال يدوي"])
    
    with tabs[0]:
        st.markdown("انسخ جدول القوائم المالية من موقع **أرقام** أو **تداول** وألصقه هنا:")
        pasted = st.text_area("لصق الجدول", height=150)
        if pasted and st.button("معالجة وحفظ (أرقام)"):
            data = parse_pasted_text(pasted)
            if data:
                c = 0
                for row in data:
                    save_financial_row(symbol, f"{row['year']}-12-31", row, "Argaam_Paste")
                    c += 1
                st.success(f"تم حفظ {c} سنوات!")
                st.rerun()
            else: st.error("صيغة الجدول غير واضحة.")

    with tabs[1]:
        f = st.file_uploader("ملف CSV/Excel", type=['csv', 'xlsx'])
        if f and st.button("رفع الملف"):
            # (نفس كود معالجة الملفات السابق يمكن وضعه هنا)
            st.warning("تأكد من توافق أسماء الأعمدة")

    with tabs[2]:
        with st.form("manual"):
            y = st.number_input("السنة", value=2024)
            rev = st.number_input("الإيرادات")
            net = st.number_input("صافي الربح")
            if st.form_submit_button("حفظ"):
                save_financial_row(symbol, f"{y}-12-31", {'revenue':rev, 'net_income':net}, "Manual")
                st.success("تم")
                st.rerun()

    # العرض
    df = get_stored_financials(symbol)
    if not df.empty:
        df['year'] = pd.to_datetime(df['date']).dt.year
        df = df.sort_values('year')
        
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 📊 النمو المالي")
            if 'revenue' in df.columns and 'net_income' in df.columns:
                chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'])
                fig = px.bar(chart_df, x='year', y='value', color='variable', barmode='group')
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("##### 📑 الأرقام")
            st.dataframe(df[['year', 'revenue', 'net_income']].set_index('year'), use_container_width=True)

# ... (دوال قاعدة البيانات Get/Save تبقى كما هي) ...
def save_financial_row(symbol, date_str, row, source):
    # (نفس دالة الحفظ السابقة)
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
