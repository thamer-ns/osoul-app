import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from database import execute_query, get_db

# === 1. جلب البيانات (Yfinance First) ===
def fetch_financials_yfinance(symbol):
    """محاولة جلب القوائم المالية من Yahoo Finance"""
    try:
        ticker_sym = f"{symbol.replace('.SR','').strip()}.SR"
        stock = yf.Ticker(ticker_sym)
        # جلب القوائم السنوية
        fin = stock.financials.T # Income Statement
        bs = stock.balance_sheet.T # Balance Sheet
        cf = stock.cashflow.T # Cash Flow
        
        # دمج البيانات حسب السنة
        data = []
        # نأخذ آخر 4 سنوات
        years = fin.index[:4] 
        
        for date_idx in years:
            row = {}
            row['year'] = date_idx.year
            row['revenue'] = fin.loc[date_idx].get('Total Revenue', 0)
            row['net_income'] = fin.loc[date_idx].get('Net Income', 0)
            row['total_assets'] = bs.loc[date_idx].get('Total Assets', 0) if date_idx in bs.index else 0
            row['total_equity'] = bs.loc[date_idx].get('Stockholders Equity', 0) if date_idx in bs.index else 0
            row['operating_cash_flow'] = cf.loc[date_idx].get('Operating Cash Flow', 0) if date_idx in cf.index else 0
            data.append(row)
            
        return data
    except Exception as e:
        return []

def get_fundamental_ratios(symbol):
    """حساب المؤشرات الأساسية"""
    # نحاول جلب البيانات المخزنة
    df = get_stored_financials(symbol)
    metrics = {"Score": 0, "Opinions": []}
    
    if df.empty:
        metrics["Opinions"].append("⚠️ لا توجد بيانات مالية محفوظة.")
        return metrics

    latest = df.sort_values('date').iloc[-1]
    
    # حساب بعض النسب البسيطة
    if latest['revenue'] > 0:
        net_margin = (latest['net_income'] / latest['revenue']) * 100
        metrics['Profit_Margin'] = net_margin
        if net_margin > 15: metrics['Score'] += 2
        
    return metrics

# === 2. واجهة المستخدم ===
def render_financial_dashboard_ui(symbol):
    st.markdown("### 📥 البيانات المالية")
    
    tab1, tab2 = st.tabs(["☁️ جلب تلقائي (Yahoo)", "✍️ إدخال يدوي"])
    
    with tab1:
        if st.button("جلب البيانات من الإنترنت"):
            with st.spinner("جاري الاتصال بـ Yahoo Finance..."):
                data = fetch_financials_yfinance(symbol)
                if data:
                    c = 0
                    for row in data:
                        save_financial_row(symbol, f"{row['year']}-12-31", row, "Yahoo_API")
                        c += 1
                    st.success(f"تم تحديث {c} سنوات بنجاح!")
                    st.rerun()
                else:
                    st.error("فشل الجلب التلقائي. يرجى استخدام الإدخال اليدوي.")

    with tab2:
        with st.form("manual_fin"):
            c1, c2, c3 = st.columns(3)
            y = c1.number_input("السنة", value=2025, step=1)
            rev = c2.number_input("الإيرادات")
            net = c3.number_input("صافي الربح")
            if st.form_submit_button("حفظ"):
                save_financial_row(symbol, f"{y}-12-31", {'revenue':rev, 'net_income':net}, "Manual")
                st.success("تم الحفظ"); st.rerun()

    # عرض البيانات
    df = get_stored_financials(symbol)
    if not df.empty:
        df['year'] = pd.to_datetime(df['date']).dt.year
        df = df.sort_values('year')
        st.bar_chart(df, x='year', y=['revenue', 'net_income'])
        st.dataframe(df[['year', 'revenue', 'net_income', 'source']], use_container_width=True)

# === دوال قاعدة البيانات المساعدة ===
def save_financial_row(symbol, date_str, row, source):
    query = """
        INSERT INTO FinancialStatements 
        (symbol, period_type, date, revenue, net_income, total_assets, total_equity, operating_cash_flow, source)
        VALUES (%s, 'Annual', %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, period_type, date) DO UPDATE SET
        revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income, source=EXCLUDED.source;
    """
    vals = (symbol, date_str, row.get('revenue',0), row.get('net_income',0), 
            row.get('total_assets',0), row.get('total_equity',0), row.get('operating_cash_flow',0), source)
    execute_query(query, vals)

def get_stored_financials(symbol):
    with get_db() as conn:
        if conn:
            try: return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol = %s", conn, params=(symbol,))
            except: pass
    return pd.DataFrame()
