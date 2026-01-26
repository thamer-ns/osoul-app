import pandas as pd
import streamlit as st
import io
import yfinance as yf
from database import execute_query, fetch_table, get_db
from market_data import fetch_price_from_google, get_ticker_symbol

# === 1. جلب المؤشرات (يدوي + ياهو) ===
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, 
        "Current_Price": 0.0, "Fair_Value": None, 
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    # 1. السعر الحالي
    price = fetch_price_from_google(symbol)
    metrics["Current_Price"] = price
    
    # 2. محاولة جلب بيانات من ياهو للمساعدة
    try:
        ticker = yf.Ticker(get_ticker_symbol(symbol))
        info = ticker.info
        metrics['P/E'] = info.get('trailingPE')
        metrics['P/B'] = info.get('priceToBook')
        metrics['ROE'] = info.get('returnOnEquity', 0) * 100
        
        # حساب القيمة العادلة (Graham)
        eps = info.get('trailingEps', 0)
        bv = info.get('bookValue', 0)
        if eps > 0 and bv > 0:
            metrics['Fair_Value'] = (22.5 * eps * bv) ** 0.5
            
    except: pass

    # 3. التقييم
    score = 0
    if metrics['P/E'] and 0 < metrics['P/E'] < 20: score += 2
    if metrics['P/B'] and metrics['P/B'] < 2: score += 2
    if metrics['ROE'] and metrics['ROE'] > 15: score += 3
    if metrics['Fair_Value'] and price < metrics['Fair_Value']: score += 3
    
    metrics['Score'] = min(score, 10)
    metrics['Rating'] = "شراء قوي 💎" if score >= 8 else "جيدة ✅" if score >= 5 else "مخاطرة ⚠️"
    
    return metrics

# === 2. الاستيراد الذكي (لصق) ===
def parse_pasted_text(raw_text):
    try:
        df = pd.read_csv(io.StringIO(raw_text), sep='\t')
        if len(df.columns) <= 1: df = pd.read_csv(io.StringIO(raw_text), sep=r'\s+', engine='python')
        df.columns = df.columns.str.strip().str.lower()
        df_T = df.set_index(df.columns[0]).T; df_T.reset_index(inplace=True)
        results = []
        for _, row in df_T.iterrows():
            year_str = str(row['index']); year = ''.join(filter(str.isdigit, year_str))
            if len(year) == 4:
                def gv(ks):
                    for c in df_T.columns:
                        if any(k in str(c) for k in ks):
                            v = str(row[c]).replace(',','').replace('(','-').replace(')','')
                            try: return float(v)
                            except: continue
                    return 0.0
                data = {'year':year, 'revenue':gv(['إيرادات','Revenue']), 'net_income':gv(['صافي','Net Income']), 'total_equity':gv(['حقوق','Equity'])}
                if data['revenue']!=0: results.append(data)
        return results
    except: return []

# === 3. الواجهة (مع ياهو) ===
def render_financial_dashboard_ui(symbol):
    st.markdown("#### 📥 إدارة البيانات المالية")
    
    with st.expander("خيارات الجلب والتحديث", expanded=True):
        t1, t2, t3 = st.tabs(["🌐 جلب آلي (Yahoo)", "📋 نسخ ولصق (أرقام)", "✍️ يدوي"])
        
        with t1:
            if st.button("سحب البيانات من Yahoo Finance", use_container_width=True):
                try:
                    tk = yf.Ticker(get_ticker_symbol(symbol))
                    inc = tk.income_stmt.T; bal = tk.balance_sheet.T
                    if not inc.empty:
                        c = 0
                        for d, r in inc.iterrows():
                            rev = r.get('Total Revenue', 0)
                            net = r.get('Net Income', 0)
                            eq = 0
                            if not bal.empty and d in bal.index: eq = bal.loc[d].get('Stockholders Equity', 0)
                            save_financial_row(symbol, d.strftime('%Y-%m-%d'), {'revenue':rev, 'net_income':net, 'total_equity':eq}, "Yahoo")
                            c+=1
                        st.success(f"تم تحديث {c} سنوات"); st.rerun()
                    else: st.warning("لم نجد بيانات في ياهو")
                except Exception as e: st.error(f"خطأ: {e}")

        with t2:
            txt = st.text_area("لصق الجدول من أرقام", height=100)
            if txt and st.button("معالجة"):
                data = parse_pasted_text(txt)
                if data:
                    for r in data: save_financial_row(symbol, f"{r['year']}-12-31", r, "Paste")
                    st.success("تم"); st.rerun()
                else: st.error("فشلت القراءة")

        with t3:
            with st.form("man"):
                y = st.number_input("السنة", 2020, 2030, 2024)
                r = st.number_input("الإيرادات"); n = st.number_input("الصافي")
                if st.form_submit_button("حفظ"):
                    save_financial_row(symbol, f"{y}-12-31", {'revenue':r, 'net_income':n}, "Manual")
                    st.success("تم"); st.rerun()

    df = get_stored_financials(symbol)
    if not df.empty:
        st.markdown("##### 📊 السجل المالي")
        disp = df[['date','revenue','net_income']].copy()
        disp['date'] = pd.to_datetime(disp['date']).dt.year
        st.dataframe(disp.set_index('date'), use_container_width=True)

def save_financial_row(symbol, date, row, src="Manual"):
    q = "INSERT INTO FinancialStatements (symbol, date, revenue, net_income, total_equity, period_type, source) VALUES (%s,%s,%s,%s,%s,'Annual',%s) ON CONFLICT (symbol, period_type, date) DO UPDATE SET revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income"
    execute_query(q, (symbol, date, row.get('revenue',0), row.get('net_income',0), row.get('total_equity',0), src))

def get_stored_financials(symbol):
    with get_db() as conn:
        try: return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol=%s ORDER BY date", conn, params=(symbol,))
        except: return pd.DataFrame()

def get_thesis(s): 
    with get_db() as c: 
        try: return pd.read_sql("SELECT * FROM InvestmentThesis WHERE symbol=%s", c, params=(s,)).iloc[0]
        except: return None
def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text", (s,t,tg,r))
