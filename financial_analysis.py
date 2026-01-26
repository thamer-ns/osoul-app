import pandas as pd
import streamlit as st
import io
from database import execute_query, fetch_table, get_db
from market_data import fetch_price_from_google

# === 1. جلب المؤشرات وحساب التقييم ===
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, 
        "Current_Price": 0.0, "Fair_Value": None, 
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    # جلب السعر الحالي
    price = fetch_price_from_google(symbol)
    metrics["Current_Price"] = price
    
    # جلب البيانات التاريخية
    df = get_stored_financials(symbol)
    
    if not df.empty:
        # أخذ آخر سنة متوفرة
        latest = df.sort_values('date').iloc[-1]
        
        # استخراج الأرقام (مع الحماية من الصفر)
        net_income = latest.get('net_income', 0)
        equity = latest.get('total_equity', 0)
        assets = latest.get('total_assets', 0)
        
        # حسابات تقريبية (نفترض عدد أسهم ثابت للتبسيط أو نجلبه مستقبلاً)
        # هنا سنستخدم صافي الدخل والقيمة الدفترية مباشرة للتقييم
        
        score = 0
        opinions = []
        
        # 1. تقييم مكرر الربحية (P/E) - نحتاج ربح السهم
        # للتبسيط سنعتمد على النمو في الدخل
        if net_income > 0:
            score += 2
            opinions.append("الشركة تحقق أرباحاً")
        
        # 2. العائد على الحقوق (ROE)
        if equity > 0:
            roe = (net_income / equity) * 100
            metrics['ROE'] = roe
            if roe > 15: 
                score += 3
                opinions.append("عائد على الحقوق ممتاز (>15%)")
            elif roe > 10:
                score += 1
        
        # 3. القيمة العادلة (Graham Formula Simplified)
        # Fair Value = Sqrt(22.5 * EPS * BVPS)
        # سنحسبها تقريبياً إذا توفرت البيانات
        if net_income > 0 and equity > 0:
            # افتراض عدد أسهم 100 مليون لغرض المثال فقط إذا لم يتوفر
            # في النسخة المطورة نربط عدد الأسهم الحقيقي
            pass 

        metrics['Score'] = min(score, 10)
        if score >= 7: metrics['Rating'] = "ممازة 💎"
        elif score >= 4: metrics['Rating'] = "جيدة ✅"
        else: metrics['Rating'] = "مخاطرة ⚠️"
        
        metrics['Opinions'] = opinions

    return metrics

# === 2. الذكاء الصناعي للصق (Argaam Parser) ===
def parse_pasted_text(raw_text):
    """تحويل النص المنسوخ من أرقام/تداول إلى بيانات"""
    try:
        # محاولة قراءة النص كجدول
        df = pd.read_csv(io.StringIO(raw_text), sep='\t')
        if len(df.columns) <= 1:
             df = pd.read_csv(io.StringIO(raw_text), sep=r'\s+', engine='python')

        # تنظيف العناوين
        df.columns = df.columns.str.strip().str.lower()
        
        # قلب الجدول (لأن المواقع تعرض السنوات في الأعمدة)
        # نجعل الصفوف أعمدة
        df_T = df.set_index(df.columns[0]).T
        df_T.reset_index(inplace=True)
        
        results = []
        for _, row in df_T.iterrows():
            # محاولة استخراج السنة من النص (مثلاً "2023" أو "ديسمبر 2023")
            year_str = str(row['index'])
            year = ''.join(filter(str.isdigit, year_str))
            
            # نقبل السنة إذا كانت 4 أرقام
            if len(year) == 4:
                def get_val(keywords):
                    for col in df_T.columns:
                        if any(k in str(col) for k in keywords):
                            val = str(row[col])
                            # تنظيف الرقم (حالة الأقواس تعني سالب)
                            is_negative = '(' in val or ')' in val
                            val = val.replace(',', '').replace('(', '').replace(')', '')
                            try: 
                                f_val = float(val)
                                return -f_val if is_negative else f_val
                            except: continue
                    return 0.0

                data_row = {
                    'year': year,
                    'revenue': get_val(['إيرادات', 'مبيعات', 'Revenue']),
                    'net_income': get_val(['صافي', 'الربح', 'Net Income']),
                    'total_assets': get_val(['أصول', 'Assets', 'موجودات']),
                    'total_equity': get_val(['حقوق', 'Equity']),
                    'oper_cash': get_val(['تشغيلي', 'Operating'])
                }
                # نضيف الصف فقط إذا كان فيه بيانات حقيقية
                if data_row['revenue'] != 0 or data_row['net_income'] != 0:
                    results.append(data_row)
        return results
    except Exception as e:
        print(f"Error parsing: {e}")
        return []

# === 3. واجهة القوائم (التي تحبها) ===
def render_financial_dashboard_ui(symbol):
    st.markdown("#### 📥 بيانات القوائم المالية")
    
    # منطقة الأدوات
    with st.expander("إضافة / تحديث البيانات (نسخ ولصق)", expanded=False):
        t1, t2 = st.tabs(["📋 نسخ من (أرقام/تداول)", "✍️ إدخال يدوي"])
        
        with t1:
            st.info("طريقة الاستخدام: اذهب لموقع أرقام -> القوائم المالية -> ظلل الجدول -> انسخ -> الصق هنا")
            txt = st.text_area("لصق الجدول هنا", height=150)
            if txt and st.button("⚡ معالجة وحفظ البيانات"):
                data = parse_pasted_text(txt)
                if data:
                    c = 0
                    for r in data:
                        save_financial_row(symbol, f"{r['year']}-12-31", r)
                        c += 1
                    st.success(f"تم بنجاح استيراد وحفظ بيانات {c} سنوات!"); st.rerun()
                else: st.error("لم نتمكن من قراءة الجدول، تأكد من النسخ بشكل صحيح.")
        
        with t2:
            with st.form("manual_fin"):
                c1, c2 = st.columns(2)
                y = c1.number_input("السنة", 2015, 2030, 2024)
                rev = c2.number_input("الإيرادات (مليون)")
                c3, c4 = st.columns(2)
                net = c3.number_input("صافي الربح (مليون)")
                eq = c4.number_input("حقوق المساهمين (مليون)")
                if st.form_submit_button("حفظ"):
                    save_financial_row(symbol, f"{y}-12-31", {'revenue': rev*1000000, 'net_income': net*1000000, 'total_equity': eq*1000000})
                    st.success("تم الحفظ"); st.rerun()

    # عرض الجدول
    df = get_stored_financials(symbol)
    if not df.empty:
        st.markdown("##### 📊 السجل التاريخي")
        # تنسيق العرض
        disp_df = df[['date', 'revenue', 'net_income', 'total_equity']].copy()
        disp_df['date'] = pd.to_datetime(disp_df['date']).dt.year
        disp_df.rename(columns={'date': 'السنة', 'revenue': 'الإيرادات', 'net_income': 'صافي الربح', 'total_equity': 'الحقوق'}, inplace=True)
        st.dataframe(disp_df.set_index('السنة'), use_container_width=True)
    else:
        st.warning("لا توجد بيانات محفوظة لهذا السهم. استخدم أداة النسخ أعلاه.")

# === دوال قاعدة البيانات ===
def save_financial_row(symbol, date, row):
    # دالة حفظ ذكية تحدث البيانات إذا كانت موجودة
    q = """
        INSERT INTO FinancialStatements (symbol, date, revenue, net_income, total_assets, total_equity, period_type, source) 
        VALUES (%s, %s, %s, %s, %s, %s, 'Annual', 'SmartPaste')
        ON CONFLICT (symbol, period_type, date) DO UPDATE SET 
        revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income, total_equity=EXCLUDED.total_equity
    """
    vals = (
        symbol, date, 
        row.get('revenue',0), row.get('net_income',0), 
        row.get('total_assets',0), row.get('total_equity',0)
    )
    execute_query(q, vals)

def get_stored_financials(symbol):
    with get_db() as conn:
        try: return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol=%s ORDER BY date ASC", conn, params=(symbol,))
        except: return pd.DataFrame()

# دوال مساعدة للأطروحة
def get_thesis(symbol):
    with get_db() as conn:
        try: 
            df = pd.read_sql("SELECT * FROM InvestmentThesis WHERE symbol=%s", conn, params=(symbol,))
            return df.iloc[0] if not df.empty else None
        except: return None

def save_thesis(symbol, text, target, rec):
    q = """
        INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation, last_updated)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (symbol) DO UPDATE SET 
        thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price
    """
    execute_query(q, (symbol, text, target, rec))
