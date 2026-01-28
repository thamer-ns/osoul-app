import pandas as pd
import streamlit as st
import io
import yfinance as yf
import plotly.express as px
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

def get_fundamental_ratios(symbol):
    metrics = {"P/E": None, "P/B": None, "ROE": None, "Fair_Value": None, "Score": 0, "Rating": "N/A"}
    price = fetch_price_from_google(symbol)
    try:
        t = yf.Ticker(get_ticker_symbol(symbol)); i = t.info
        metrics['P/E'] = i.get('trailingPE') or i.get('forwardPE')
        metrics['P/B'] = i.get('priceToBook')
        metrics['ROE'] = (i.get('returnOnEquity', 0) or 0) * 100
        eps = i.get('trailingEps', 0); bv = i.get('bookValue', 0)
        if eps and bv and eps > 0 and bv > 0: metrics['Fair_Value'] = (22.5 * eps * bv)**0.5
    except: pass
    
    s = 0
    if metrics['P/E'] and 0 < metrics['P/E'] < 20: s += 2
    if metrics['P/B'] and 0 < metrics['P/B'] < 2.5: s += 2
    if metrics['ROE'] and metrics['ROE'] > 12: s += 3
    if metrics['Fair_Value'] and price < metrics['Fair_Value']: s += 3
    metrics['Score'] = min(s, 10)
    metrics['Rating'] = "ممتازة" if s>=8 else "جيدة" if s>=5 else "مخاطرة"
    return metrics

def parse_pasted_text(txt):
    try:
        df = pd.read_csv(io.StringIO(txt), sep='\t')
        if df.shape[1] < 2: df = pd.read_csv(io.StringIO(txt), sep=r'\s+', engine='python')
        df.columns = df.columns.str.strip().str.lower()
        df = df.set_index(df.columns[0]).T.reset_index(); res = []
        for _, r in df.iterrows():
            y = ''.join(filter(str.isdigit, str(r['index'])))
            if len(y)==4:
                def g(k): 
                    for c in df.columns: 
                        if any(x in str(c) for x in k): return float(str(r[c]).replace(',','').replace('(','-').replace(')',''))
                    return 0.0
                res.append({'year':y, 'revenue':g(['إيرادات','Revenue']), 'net_income':g(['صافي','Net'])})
        return res
    except: return []

def render_financial_dashboard_ui(symbol):
    st.markdown("#### 📥 القوائم"); 
    with st.expander("ادخال بيانات"):
        t1, t2, t3 = st.tabs(["Yahoo", "نسخ", "يدوي"])
        with t1:
            if st.button("سحب"):
                try:
                    t = yf.Ticker(get_ticker_symbol(symbol)); inc = t.income_stmt.T
                    for d, r in inc.iterrows(): save_financial_row(symbol, d.strftime('%Y-%m-%d'), {'revenue': r.get('Total Revenue',0), 'net_income': r.get('Net Income',0)})
                    st.success("تم")
                except: st.error("فشل")
        with t2:
            txt = st.text_area("لصق"); 
            if txt and st.button("معالجة"): 
                for r in parse_pasted_text(txt): save_financial_row(symbol, f"{r['year']}-12-31", r)
                st.success("تم")
        with t3:
            with st.form("m"):
                y=st.number_input("سنة",2024); r=st.number_input("ايراد"); n=st.number_input("صافي")
                if st.form_submit_button("حفظ"): save_financial_row(symbol,f"{y}-12-31",{'revenue':r,'net_income':n}); st.success("تم")

    df = get_stored_financials(symbol)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']); df = df.sort_values('date')
        df['Year'] = df['date'].dt.year.astype(str)
        st.plotly_chart(px.bar(df, x='Year', y=['revenue', 'net_income'], barmode='group'), use_container_width=True)
        st.dataframe(df)

def save_financial_row(s, d, r):
    try: rev = float(r.get('revenue', 0)); net = float(r.get('net_income', 0))
    except: rev = 0.0; net = 0.0
    execute_query("INSERT INTO FinancialStatements (symbol, date, revenue, net_income, period_type) VALUES (%s,%s,%s,%s,'Annual') ON CONFLICT (symbol, date, period_type) DO UPDATE SET revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income", (s,d,rev,net))

def get_stored_financials(s):
    try: return fetch_table("FinancialStatements").query(f"symbol == '{s}'")
    except: return pd.DataFrame()

def get_thesis(s): 
    try: df = fetch_table("InvestmentThesis"); return df[df['symbol'] == s].iloc[0] if not df.empty else None
    except: return None

def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price, recommendation=EXCLUDED.recommendation", (s,t,float(tg),r))
