import pandas as pd
import streamlit as st
import plotly.express as px
import io
from database import execute_query, get_db, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol
from config import DEFAULT_COLORS

# === أدوات مساعدة ===
def safe_float(val):
    try: return float(val)
    except: return 0.0

# === 1. جلب مؤشرات أساسية ===
@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Score": 0, 
        "Rating": "تحليل يدوي", "Opinions": []
    }
    
    # محاولة جلب السعر
    try:
        price = fetch_price_from_google(symbol)
        metrics["Current_Price"] = price
    except: pass

    # جلب البيانات المالية المحفوظة
    try:
        df = get_stored_financials(symbol)
        if not df.empty:
            latest = df.sort_values('date').iloc[-1]
            metrics["Opinions"].append(f"آخر بيانات مسجلة: {latest['year']}")
            
            # حسابات بسيطة إذا توفرت البيانات
            if metrics["Current_Price"] > 0 and latest['eps'] > 0:
                metrics["P/E"] = metrics["Current_Price"] / latest['eps']
    except: pass

    metrics["Opinions"].append("البيانات تعتمد على الإدخال اليدوي أو النسخ")
    return metrics

# === 2. واجهة المستخدم ===
def render_financial_dashboard_ui(symbol):
    st.markdown("### 📥 البيانات المالية")
    
    # تبويبات الإدخال
    t1, t2 = st.tabs(["نسخ (أرقام/تداول)", "إدخال يدوي"])
    
    with t1:
        st.markdown("انسخ الجدول من موقع أرقام وألصقه هنا:")
        pasted = st.text_area("مساحة اللصق", height=150)
        if pasted and st.button("معالجة وحفظ"):
            try:
                # معالجة بسيطة للنص المنسوخ
                rows = pasted.split('\n')
                st.success("تم استلام النص، جاري التطوير لمعالجته بدقة.")
            except: st.error("صيغة غير مدعومة")

    with t2:
        with st.form("manual_fin"):
            c1, c2, c3 = st.columns(3)
            year = c1.number_input("السنة", 2024, 2030, 2024)
            rev = c2.number_input("الإيرادات")
            net = c3.number_input("صافي الربح")
            if st.form_submit_button("حفظ"):
                save_financial_row(symbol, f"{year}-12-31", {'revenue': rev, 'net_income': net}, "Manual")
                st.success("تم الحفظ")

    # عرض البيانات
    df = get_stored_financials(symbol)
    if not df.empty:
        df['year'] = pd.to_datetime(df['date']).dt.year
        df = df.sort_values('year')
        
        c_chart, c_table = st.columns([2, 1])
        with c_chart:
            st.markdown("##### 📊 النمو المالي")
            if 'revenue' in df.columns and 'net_income' in df.columns:
                chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'], var_name='المؤشر', value_name='القيمة')
                fig = px.bar(chart_df, x='year', y='القيمة', color='المؤشر', barmode='group')
                st.plotly_chart(fig, use_container_width=True)
        with c_table:
            st.dataframe(df[['year', 'revenue', 'net_income']], hide_index=True)
    else:
        st.info("لا توجد بيانات مالية محفوظة لهذا السهم.")

# === دوال قاعدة البيانات ===
def save_financial_row(symbol, date_str, row, source):
    query = """
        INSERT INTO FinancialStatements 
        (symbol, period_type, date, revenue, net_income, source)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    # ملاحظة: في Supabase يفضل استخدام INSERT بسيط للتجربة
    try:
        execute_query(query, (symbol, 'Annual', date_str, safe_float(row.get('revenue')), safe_float(row.get('net_income')), source))
    except: pass

def get_stored_financials(symbol):
    with get_db() as conn:
        if conn:
            try: return pd.read_sql(f"SELECT * FROM FinancialStatements WHERE symbol = '{symbol}' ORDER BY date ASC", conn)
            except: pass
    return pd.DataFrame()

# === الأطروحة الاستثمارية ===
def save_thesis(symbol, text, target, rec):
    query = "INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s, %s, %s, %s)"
    try: execute_query(query, (symbol, text, target, rec))
    except: pass # قد يحتاج لتحديث بدلاً من إضافة

def get_thesis(symbol):
    try:
        df = fetch_table("InvestmentThesis")
        if not df.empty:
            row = df[df['symbol'] == symbol]
            if not row.empty: return row.iloc[-1]
    except: pass
    return None
