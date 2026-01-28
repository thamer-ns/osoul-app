import pandas as pd
import streamlit as st
import io
import yfinance as yf
import plotly.express as px
import numpy as np
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol

# ==============================================================
# الجزء الأول: الذكاء المالي (جراهام، بيوتروسكي، القيمة العادلة)
# ==============================================================

def calculate_piotroski_score(info, financials, balance_sheet, cashflow):
    score = 0
    try:
        # محاولة التعامل مع البيانات سواء كانت من Yahoo أو مدخلة يدوياً
        net_income = financials.loc['Net Income'].iloc[0] if 'Net Income' in financials.index else 0
        net_income_prev = financials.loc['Net Income'].iloc[1] if 'Net Income' in financials.index and len(financials.columns) > 1 else 0
        
        op_cash = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
        
        assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 1
        assets_prev = balance_sheet.loc['Total Assets'].iloc[1] if 'Total Assets' in balance_sheet.index and len(balance_sheet.columns) > 1 else 1

        roa = net_income / assets
        roa_prev = net_income_prev / assets_prev
        
        # 1. الربحية
        if net_income > 0: score += 1
        if op_cash > 0: score += 1
        if roa > roa_prev: score += 1
        if op_cash > net_income: score += 1

        # 2. الرافعة والسيولة (بيانات تقريبية)
        score += 1 # افتراضي للديون
        score += 1 # افتراضي للسيولة

        # 3. الكفاءة
        score += 1 
        
    except:
        pass 
    return min(score, 9) # الحد الأقصى 9

def get_advanced_fundamental_ratios(symbol):
    metrics = {
        "Fair_Value_Graham": None, "Piotroski_Score": 0,
        "Financial_Health": "غير معروف", "Dividend_Safety": "N/A",
        "Score": 0, "Rating": "N/A" # للتوافق مع الكود القديم
    }
    
    clean_sym = get_ticker_symbol(symbol)
    price = fetch_price_from_google(symbol)
    
    try:
        t = yf.Ticker(clean_sym)
        info = t.info
        
        # معادلة جراهام
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        if eps and bvps and eps > 0 and bvps > 0:
            metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
            
        # بيوتروسكي (مبسط)
        fin = t.financials
        bs = t.balance_sheet
        cf = t.cashflow
        if not fin.empty and not bs.empty:
            metrics['Piotroski_Score'] = calculate_piotroski_score(info, fin, bs, cf)
            
        # الحالة العامة
        s = metrics['Piotroski_Score']
        if s >= 7: metrics['Financial_Health'] = "💪 قوي جداً"
        elif s >= 5: metrics['Financial_Health'] = "👌 مستقر"
        else: metrics['Financial_Health'] = "⚠️ ضعيف"

        # للتوافق مع العرض القديم
        metrics['Score'] = s + (1 if metrics.get('Fair_Value_Graham',0) > price else 0)
        metrics['Rating'] = metrics['Financial_Health']

    except Exception as e:
        print(f"Analysis Error: {e}")
        
    return metrics, price

# ==============================================================
# الجزء الثاني: أدوات القوائم المالية القديمة (إدخال، تخزين، رسم)
# ==============================================================

def parse_pasted_text(txt):
    """تحليل النص المنسوخ من ملفات Excel أو PDF"""
    try:
        df = pd.read_csv(io.StringIO(txt), sep='\t')
        if df.shape[1] < 2: df = pd.read_csv(io.StringIO(txt), sep=r'\s+', engine='python')
        
        # تنظيف العناوين
        df.columns = df.columns.str.strip().str.lower()
        
        # محاولة قلب الجدول ليصبح (سنة - بند)
        df = df.set_index(df.columns[0]).T.reset_index()
        
        res = []
        for _, r in df.iterrows():
            # استخراج السنة من النص
            y = ''.join(filter(str.isdigit, str(r['index'])))
            if len(y) == 4:
                # البحث عن الكلمات المفتاحية
                def g(keywords): 
                    for c in df.columns: 
                        if any(k in str(c) for k in keywords): 
                            val = str(r[c]).replace(',', '').replace('(', '-').replace(')', '')
                            try: return float(val)
                            except: return 0.0
                    return 0.0
                
                res.append({
                    'year': y, 
                    'revenue': g(['إيرادات', 'revenue', 'sales', 'مبيعات']), 
                    'net_income': g(['صافي', 'net income', 'profit', 'ربح'])
                })
        return res
    except: return []

def save_financial_row(s, d, r):
    try: rev = float(r.get('revenue', 0)); net = float(r.get('net_income', 0))
    except: rev = 0.0; net = 0.0
    execute_query(
        "INSERT INTO FinancialStatements (symbol, date, revenue, net_income, period_type) VALUES (%s,%s,%s,%s,'Annual') ON CONFLICT (symbol, date, period_type) DO UPDATE SET revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income", 
        (s, d, rev, net)
    )

def get_stored_financials(s):
    try: return fetch_table("FinancialStatements").query(f"symbol == '{s}'")
    except: return pd.DataFrame()

# ==============================================================
# الجزء الثالث: واجهة العرض الموحدة (UI)
# ==============================================================

def render_financial_dashboard_ui(symbol):
    # 1. عرض التحليل الذكي المتقدم (الجديد)
    st.markdown("### 🧠 التحليل المالي الذكي")
    metrics, curr_price = get_advanced_fundamental_ratios(symbol)
    
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("السعر الحالي", f"{curr_price:,.2f}")
    with m2: 
        fv = metrics.get('Fair_Value_Graham')
        st.metric("قيمة جراهام العادلة", f"{fv:,.2f}" if fv else "-", 
                  delta=f"{((fv-curr_price)/curr_price)*100:.1f}%" if fv else None)
    with m3: st.metric("المتانة (F-Score)", f"{metrics['Piotroski_Score']} / 9", metrics['Financial_Health'])
    with m4: st.metric("التوصية الآلية", "شراء" if (fv and curr_price < fv * 0.9) else "احتفاظ")

    st.markdown("---")

    # 2. عرض البيانات المخزنة والرسوم البيانية (القديم المطور)
    st.markdown("### 📊 نمو الإيرادات والأرباح (بيانات تاريخية)")
    df = get_stored_financials(symbol)
    
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df['Year'] = df['date'].dt.year.astype(str)
        
        # رسم بياني محسن
        fig = px.bar(df, x='Year', y=['revenue', 'net_income'], barmode='group', 
                     labels={'value': 'القيمة (ريال)', 'variable': 'المؤشر'},
                     color_discrete_map={'revenue': '#0052CC', 'net_income': '#006644'})
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("عرض الجدول الرقمي"):
            st.dataframe(df[['date', 'revenue', 'net_income']].style.format("{:,.0f}"))
    else:
        st.info("لا توجد قوائم مالية محفوظة لهذا السهم. يمكنك إضافتها بالأسفل.")

    # 3. أدوات الإدخال (القديمة)
    st.markdown("---")
    with st.expander("📥 إدخال قوائم مالية جديدة"):
        t1, t2, t3 = st.tabs(["سحب آلي (Yahoo)", "نسخ ولصق (Excel)", "إدخال يدوي"])
        
        # سحب آلي
        with t1:
            if st.button("سحب القوائم من Yahoo Finance"):
                try:
                    t = yf.Ticker(get_ticker_symbol(symbol))
                    inc = t.income_stmt.T
                    count = 0
                    for d, r in inc.iterrows():
                        save_financial_row(symbol, d.strftime('%Y-%m-%d'), 
                                         {'revenue': r.get('Total Revenue', 0), 
                                          'net_income': r.get('Net Income', 0)})
                        count += 1
                    st.success(f"تم سحب وحفظ {count} سنوات بنجاح!")
                    st.rerun()
                except Exception as e: st.error(f"فشل السحب: {e}")

        # نسخ ولصق
        with t2:
            st.write("انسخ الجدول من Excel (السنوات كأعمدة أو صفوف) والصقه هنا:")
            txt = st.text_area("منطقة اللصق", height=100)
            if txt and st.button("معالجة وحفظ النص"):
                res = parse_pasted_text(txt)
                if res:
                    for r in res: save_financial_row(symbol, f"{r['year']}-12-31", r)
                    st.success("تم الحفظ!")
                    st.rerun()
                else: st.error("لم يتم التعرف على البيانات. تأكد أن النص يحتوي على 'إيرادات' و 'صافي' وتواريخ.")

        # إدخال يدوي
        with t3:
            with st.form("manual_fin_entry"):
                c_y = st.number_input("السنة المالية", min_value=2015, max_value=2030, step=1, value=2023)
                c_rev = st.number_input("إجمالي الإيرادات", step=100000.0)
                c_net = st.number_input("صافي الربح", step=50000.0)
                if st.form_submit_button("حفظ السجل"):
                    save_financial_row(symbol, f"{c_y}-12-31", {'revenue': c_rev, 'net_income': c_net})
                    st.success("تم الحفظ")
                    st.rerun()

# دوال مساعدة للأطروحة (لضمان عمل الملف بشكل كامل)
def get_thesis(s): 
    try: df = fetch_table("InvestmentThesis"); return df[df['symbol'] == s].iloc[0] if not df.empty else None
    except: return None

def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price, recommendation=EXCLUDED.recommendation", (s,t,float(tg),r))

# دالة التوافقية (ليعمل views.py بدون تعديل)
def get_fundamental_ratios(symbol):
    m, _ = get_advanced_fundamental_ratios(symbol)
    return m
