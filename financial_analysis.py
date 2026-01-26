import pandas as pd
import streamlit as st
import io
from database import execute_query, fetch_table, get_db
from market_data import fetch_price_from_google

# === 1. جلب المؤشرات الأساسية ===
def get_fundamental_ratios(symbol):
    # قيم افتراضية
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, 
        "Current_Price": 0.0, "Fair_Value": None, 
        "Score": 0, "Rating": "تحليل يدوي", "Opinions": []
    }
    
    # محاولة جلب السعر
    price = fetch_price_from_google(symbol)
    metrics["Current_Price"] = price
    
    # محاولة جلب آخر بيانات مالية مخزنة لحساب المؤشرات
    df = get_stored_financials(symbol)
    if not df.empty:
        latest = df.sort_values('date').iloc[-1]
        try:
            eps = latest.get('net_income', 0) / 1000000 # افتراض عدد أسهم تقريبي أو يتم جلبه
            if eps > 0: metrics['P/E'] = price / eps
            metrics['Opinions'].append(f"بناءً على بيانات: {latest.get('year', 'غير معروف')}")
        except: pass

    return metrics

# === 2. معالج اللصق الذكي (Smart Paste) ===
def parse_pasted_text(raw_text):
    try:
        # محاولة القراءة كجدول
        df = pd.read_csv(io.StringIO(raw_text), sep='\t')
        if len(df.columns) <= 1:
             df = pd.read_csv(io.StringIO(raw_text), sep=r'\s+', engine='python')

        df.columns = df.columns.str.strip().str.lower()
        
        # قلب الجدول (لأن المواقع تعرض السنوات في الأعمدة)
        df_T = df.set_index(df.columns[0]).T
        df_T.reset_index(inplace=True)
        
        results = []
        for _, row in df_T.iterrows():
            # استخراج السنة من النص
            year_str = str(row['index'])
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
                    'total_assets': get_val(['أصول', 'Assets', 'موجودات']),
                    'total_equity': get_val(['حقوق', 'Equity']),
                }
                if data_row['revenue'] != 0: results.append(data_row)
        return results
    except: return []

# === 3. واجهة القوائم المالية (Dashboard UI) ===
def render_financial_dashboard_ui(symbol):
    # أدوات الإدخال
    with st.expander("📥 إدارة البيانات المالية (استيراد/تعديل)"):
        t1, t2 = st.tabs(["نسخ ولصق (أرقام)", "إدخال يدوي"])
        
        with t1:
            st.markdown("انسخ الجدول من موقع (أرقام/تداول) وألصقه هنا:")
            txt = st.text_area("منطقة اللصق", height=100)
            if txt and st.button("معالجة وحفظ"):
                data = parse_pasted_text(txt)
                if data:
                    for r in data:
                        save_financial_row(symbol, f"{r['year']}-12-31", r)
                    st.success(f"تم حفظ {len(data)} سنوات"); st.rerun()
                else: st.error("لم يتم التعرف على البيانات")
        
        with t2:
            with st.form("manual_fin"):
                c1, c2, c3 = st.columns(3)
                y = c1.number_input("السنة", 2020, 2030, 2024)
                rev = c2.number_input("الإيرادات")
                net = c3.number_input("صافي الدخل")
                if st.form_submit_button("حفظ"):
                    save_financial_row(symbol, f"{y}-12-31", {'revenue': rev, 'net_income': net})
                    st.success("تم"); st.rerun()

    # عرض الجدول
    df = get_stored_financials(symbol)
    if not df.empty:
        st.markdown("##### 📊 القوائم المالية التاريخية")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("لا توجد بيانات مالية محفوظة. استخدم الأدوات أعلاه لإضافتها.")

# === دوال القاعدة ===
def save_financial_row(symbol, date, row):
    q = """INSERT INTO FinancialStatements (symbol, date, revenue, net_income, total_assets, total_equity, period_type, source) 
           VALUES (%s, %s, %s, %s, %s, %s, 'Annual', 'Manual')
           ON CONFLICT (symbol, period_type, date) DO UPDATE SET 
           revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income"""
    execute_query(q, (symbol, date, row.get('revenue',0), row.get('net_income',0), row.get('total_assets',0), row.get('total_equity',0)))

def get_stored_financials(symbol):
    with get_db() as conn:
        try: return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol=%s ORDER BY date", conn, params=(symbol,))
        except: return pd.DataFrame()

def get_thesis(symbol): return None # يمكن تطويرها لاحقاً
def save_thesis(s, t, p, r): pass
