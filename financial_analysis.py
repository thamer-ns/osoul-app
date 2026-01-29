import pandas as pd
import streamlit as st
import io
import re
import yfinance as yf
import numpy as np
import plotly.express as px
from datetime import datetime
from database import execute_query, fetch_table
from market_data import get_ticker_symbol

# محاولة استيراد مكتبة PDF (اختياري لتجنب توقف النظام إذا لم تثبت)
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# ==============================================================
# 🧠 1. محرك معالجة النصوص والملفات (The Parsing Engine)
# ==============================================================

class FinancialParser:
    def __init__(self):
        # قاموس المصطلحات لربط النصوص العربية/الإنجليزية بقاعدة البيانات
        # هذا القاموس هو "المترجم" الذي يفهم ملفات تداول و TradingView
        self.mapping = {
            'revenue': [
                r'إجمالي الإيرادات', r'مبيعات', r'sales', r'total revenue', r'revenues', 
                r'المبيعات', r'الإيرادات', r'revenue'
            ],
            'net_income': [
                r'صافي الدخل', r'صافي الربح', r'net income', r'profit', r'net profit',
                r'الربح \(الخسارة\) للفترة', r'ربح \(خسارة\) الفترة', r'صافي الدخل العائد'
            ],
            'total_assets': [
                r'إجمالي الموجودات', r'مجموع الموجودات', r'total assets', 
                r'الموجودات', r'إجمالي الأصول'
            ],
            'total_liabilities': [
                r'إجمالي المطلوبات', r'مجموع المطلوبات', r'total liabilities', 
                r'المطلوبات', r'إجمالي الالتزامات'
            ],
            'total_equity': [
                r'إجمالي حقوق الملكية', r'مجموع حقوق الملكية', r'total equity', 
                r'حقوق المساهمين', r'total shareholders equity'
            ],
            'operating_cash_flow': [
                r'صافي التدفقات النقدية من .* التشغيلية', r'operating cash flow', 
                r'cash from operating', r'التدفقات النقدية التشغيلية', r'نقد من العمليات'
            ],
            'current_assets': [
                r'الموجودات المتداولة', r'إجمالي الموجودات المتداولة', r'current assets'
            ],
            'current_liabilities': [
                r'المطلوبات المتداولة', r'إجمالي المطلوبات المتداولة', r'current liabilities'
            ],
            'long_term_debt': [
                r'قروض طويلة الأجل', r'مطلوبات غير متداولة', r'long term debt', 
                r'non-current liabilities', r'قروض لأجل'
            ]
        }

    def _clean_number(self, val_str):
        """تنظيف الأرقام المعقدة (1.5B, (500), 1,000)"""
        if pd.isna(val_str): return 0.0
        s = str(val_str).strip().upper()
        
        # معاملات الضرب (B, M, K)
        multiplier = 1.0
        if s.endswith('B') or 'مليار' in s: multiplier = 1_000_000_000
        elif s.endswith('M') or 'مليون' in s: multiplier = 1_000_000
        elif s.endswith('K') or 'ألف' in s: multiplier = 1_000
        
        # إزالة الرموز غير الرقمية ما عدا السالب والنقطة
        s = re.sub(r'[^\d\.\-\(\)]', '', s)
        
        # معالجة الأقواس السالبة: (500) -> -500
        if '(' in s and ')' in s:
            s = s.replace('(', '-').replace(')', '')
        
        try:
            val = float(s) * multiplier
            return val
        except:
            return 0.0

    def _extract_symbol(self, text):
        """محاولة اكتشاف رمز الشركة من النص (4 أرقام)"""
        # البحث عن 4 أرقام متتالية تكون في بداية سطر أو مسبوقة بكلمة رمز
        # الأولوية للرموز السعودية (1000-9999)
        matches = re.findall(r'\b([1-9]\d{3})\b', text)
        for m in matches:
            # فلترة التواريخ (2020, 2021, etc)
            if not m.startswith('20'): 
                return f"{m}.SR"
        return None

    def _detect_format_and_parse(self, text):
        """العقل المدبر: يحدد نوع الملف (تداول أو ويب) ويوجه للمعالج المناسب"""
        lines = text.split('\n')
        
        # 1. نمط ملفات تداول (يحتوي على أكواد أقسام مثل [300100])
        if any(re.search(r'\[\d{6}\]', line) for line in lines):
            return self._parse_tadawul_style(lines)
            
        # 2. نمط الجداول العادية (TradingView / Excel)
        return self._parse_table_style(lines)

    def _parse_tadawul_style(self, lines):
        """
        خوارزمية خاصة لملفات تداول النصية المعقدة
        """
        extracted_data = {}
        dates = []
        symbol = None
        
        # 1. البحث عن الرمز والتواريخ
        for line in lines:
            if not symbol: symbol = self._extract_symbol(line)
            # البحث عن تواريخ بصيغة YYYY-MM-DD
            date_matches = re.findall(r'(\d{4}-\d{2}-\d{2})', line)
            if date_matches and not dates:
                # نأخذ التواريخ الفريدة ونرتبها (الأحدث عادة يكون العمود الأول)
                dates = sorted(list(set(date_matches)), reverse=True)[:2] 

        if not dates: 
            # محاولة البحث عن سنوات فقط
            for line in lines:
                year_matches = re.findall(r'\b(20\d{2})\b', line)
                if len(year_matches) >= 2:
                    dates = [f"{y}-12-31" for y in sorted(list(set(year_matches)), reverse=True)[:2]]
                    break

        if not dates: dates = [pd.Timestamp.now().strftime('%Y-12-31')] # احتياطي

        # 2. استخراج البيانات
        for line in lines:
            line = line.strip()
            for key, patterns in self.mapping.items():
                if any(p in line for p in patterns): # بحث سريع
                    # إذا وجدنا تطابق، نستخرج الأرقام من السطر
                    # نمط تداول: النص ثم الأرقام مفصولة بفواصل
                    nums = re.findall(r'(-?[\d,]{2,}(?:\.\d+)?)', line)
                    if not nums: continue
                    
                    clean_nums = [self._clean_number(n) for n in nums]
                    
                    # ربط الأرقام بالتواريخ (العمود الأول للتاريخ الأول، وهكذا)
                    for i, date_val in enumerate(dates):
                        if i < len(clean_nums):
                            if date_val not in extracted_data: extracted_data[date_val] = {}
                            # نأخذ الرقم الأكبر (لتجنب الأصفار أو القيم الفارغة)
                            current_val = extracted_data[date_val].get(key, 0)
                            if abs(clean_nums[i]) > abs(current_val):
                                extracted_data[date_val][key] = clean_nums[i]
                    break 
        
        results = [{'date': d, 'data': data} for d, data in extracted_data.items()]
        return results, symbol

    def _parse_table_style(self, lines):
        """
        خوارزمية للجداول المنسوخة (Excel / Web)
        """
        try:
            # تنظيف النص: استبدال المسافات المتعددة بـ Tab لمحاكاة Excel
            clean_text = "\n".join([re.sub(r' {2,}|\t', ',', line) for line in lines])
            df = pd.read_csv(io.StringIO(clean_text), header=None, on_bad_lines='skip')
            
            # البحث عن سطر التواريخ
            date_row_idx = -1
            dates = []
            
            for idx, row in df.iterrows():
                row_str = " ".join([str(x) for x in row.values])
                years = re.findall(r'\b(20\d{2})\b', row_str)
                if len(years) >= 2:
                    date_row_idx = idx
                    # استخراج التواريخ بالترتيب من الأعمدة
                    for col_idx, val in enumerate(row.values):
                        y_match = re.search(r'\b(20\d{2})\b', str(val))
                        if y_match:
                            dates.append((col_idx, f"{y_match.group(1)}-12-31"))
                    break
            
            if date_row_idx == -1: return [], self._extract_symbol("\n".join(lines[:10]))

            results_map = {} # {date: {key: val}}

            # المرور على البيانات
            for idx, row in df.iterrows():
                if idx <= date_row_idx: continue
                row_label = str(row[0])
                
                for key, patterns in self.mapping.items():
                    if any(re.search(p, row_label, re.IGNORECASE) for p in patterns):
                        # وجدنا بند مالي (مثل "Revenue")
                        for col_idx, date_val in dates:
                            if col_idx < len(row):
                                val = self._clean_number(row[col_idx])
                                if date_val not in results_map: results_map[date_val] = {}
                                results_map[date_val][key] = val
                        break
            
            final_res = [{'date': d, 'data': data} for d, data in results_map.items()]
            symbol = self._extract_symbol("\n".join(lines[:10]))
            return final_res, symbol

        except Exception as e:
            print(f"Parsing Error: {e}")
            return [], None

    def process_file_or_text(self, uploaded_file=None, text_input=None):
        """الواجهة الرئيسية للمعالجة"""
        text = ""
        
        if text_input:
            text = text_input
        elif uploaded_file:
            filename = uploaded_file.name.lower()
            try:
                if filename.endswith('.pdf'):
                    if not pdfplumber: return [], None, "مكتبة pdfplumber غير مثبتة."
                    with pdfplumber.open(uploaded_file) as pdf:
                        for page in pdf.pages:
                            text += page.extract_text() + "\n"
                            
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(uploaded_file)
                    text = df.to_string() # تحويل لجدول نصي
                    
                elif filename.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                    text = df.to_string()
            except Exception as e:
                return [], None, f"خطأ في قراءة الملف: {e}"
        
        if not text: return [], None, "لا يوجد نص للمعالجة"
        
        results, symbol = self._detect_format_and_parse(text)
        return results, symbol, None

# ==============================================================
# 📥 2. وظائف التخزين والمزامنة
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    """حفظ البيانات في قاعدة البيانات مع معالجة التكرار"""
    try:
        vals = {k: float(data.get(k, 0)) for k in [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'total_equity', 'operating_cash_flow', 'current_assets', 
            'current_liabilities', 'long_term_debt'
        ]}
        
        if sum(abs(v) for v in vals.values()) == 0: return False

        query = """
            INSERT INTO "FinancialStatements" 
            (symbol, date, period_type, source, revenue, net_income, total_assets, total_liabilities, 
             total_equity, operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) 
            DO UPDATE SET 
                revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income,
                total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities,
                total_equity=EXCLUDED.total_equity, operating_cash_flow=EXCLUDED.operating_cash_flow,
                current_assets=EXCLUDED.current_assets, current_liabilities=EXCLUDED.current_liabilities,
                long_term_debt=EXCLUDED.long_term_debt, source=EXCLUDED.source;
        """
        execute_query(query, (
            symbol, date_str, period_type, source,
            vals['revenue'], vals['net_income'], vals['total_assets'], vals['total_liabilities'],
            vals['total_equity'], vals['operating_cash_flow'], vals['current_assets'],
            vals['current_liabilities'], vals['long_term_debt']
        ))
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

def sync_auto_yahoo(symbol):
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        count = 0
        
        # منطق المعالجة (نفس الكود السابق لكن مختصر هنا للتوضيح)
        def _process(df_fin, df_bs, df_cf, p_type):
            c = 0
            if df_fin.empty: return 0
            dates = sorted(list(set(df_fin.columns) | set(df_bs.columns) | set(df_cf.columns)), reverse=True)[:6]
            for d in dates:
                try:
                    d_str = d.strftime('%Y-%m-%d')
                    # دالة مساعدة لجلب القيمة بأمان
                    def g(df, k): 
                        if df.empty: return 0
                        return df.loc[k, d] if k in df.index and d in df.columns else 0
                    
                    data = {
                        'revenue': g(df_fin, 'Total Revenue'),
                        'net_income': g(df_fin, 'Net Income'),
                        'total_assets': g(df_bs, 'Total Assets'),
                        'total_liabilities': g(df_bs, 'Total Liabilities Net Minority Interest'),
                        'total_equity': g(df_bs, 'Total Equity Gross Minority Interest'),
                        'operating_cash_flow': g(df_cf, 'Operating Cash Flow'),
                        'current_assets': g(df_bs, 'Current Assets'),
                        'current_liabilities': g(df_bs, 'Current Liabilities'),
                        'long_term_debt': g(df_bs, 'Long Term Debt')
                    }
                    if save_financial_record(symbol, d_str, data, p_type, 'Auto_Yahoo'): c += 1
                except: continue
            return c

        count += _process(t.financials, t.balance_sheet, t.cashflow, 'Annual')
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        
        return True, f"تم تحديث {count} سجلات"
    except Exception as e: return False, str(e)

# ==============================================================
# 📊 3. واجهة المستخدم (The Dashboard UI)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    # نفس دالة النسب المالية السابقة (بيتروسكي وجراهام)
    metrics = {"Fair_Value_Graham": 0.0, "Piotroski_Score": 0, "Financial_Health": "غير متوفر", "Score": 0, "Rating": "N/A", "Opinions": ""}
    df = get_stored_financials_df(symbol, 'Annual')
    if df.empty: df = get_stored_financials_df(symbol, 'Quarterly')
    if df.empty or len(df) < 1: return metrics
    
    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr
    
    try:
        score = 0
        if curr.get('net_income', 0) > 0: score += 1
        if curr.get('operating_cash_flow', 0) > 0: score += 1
        
        roa_c = curr.get('net_income', 0) / (curr.get('total_assets', 1) or 1)
        roa_p = prev.get('net_income', 0) / (prev.get('total_assets', 1) or 1)
        if roa_c > roa_p: score += 1
        
        if curr.get('operating_cash_flow', 0) > curr.get('net_income', 0): score += 1
        if curr.get('long_term_debt', 0) < prev.get('long_term_debt', 0): score += 1
        
        metrics['Piotroski_Score'] = min(score + 3, 9)
        if score >= 5: metrics['Financial_Health'] = "جيد"
        else: metrics['Financial_Health'] = "هش"
        
        # Graham
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps and eps > 0 and bvps > 0:
                metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
        except: pass
        
        metrics['Score'] = metrics['Piotroski_Score']
        metrics['Rating'] = metrics['Financial_Health']
        
    except: pass
    return metrics

# التوافقية
def get_fundamental_ratios(symbol):
    return get_advanced_fundamental_ratios(symbol)

# === وظائف الأطروحة ===
def get_thesis(s): 
    try: df = fetch_table("InvestmentThesis"); return df[df['symbol'] == s].iloc[0] if not df.empty else None
    except: return None

def save_thesis(s, t, tg, r):
    execute_query("INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET thesis_text=EXCLUDED.thesis_text, target_price=EXCLUDED.target_price, recommendation=EXCLUDED.recommendation", (s,t,float(tg),r))

# ==============================================================
# 🖥️ واجهة العرض الرئيسية
# ==============================================================

def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ استيراد البيانات"])
    
    with tab_dashboard:
        # كود عرض الداشبورد (نفس السابق)
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, label_visibility="collapsed")
        df = get_stored_financials_df(symbol, ptype)
        if df.empty:
            st.warning("⚠️ لا توجد بيانات. يرجى الذهاب لتبويب الاستيراد.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("F-Score", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
            c2.metric("Graham Value", f"{metrics.get('Fair_Value_Graham', 0):.2f}")
            c3.write(metrics.get('Opinions', ''))
            
            try:
                plot_df = df.copy()
                plot_df['Year'] = plot_df['date'].dt.strftime('%Y-%m')
                fig = px.bar(plot_df.sort_values('date'), x='Year', y=['revenue', 'net_income'], barmode='group')
                st.plotly_chart(fig, use_container_width=True)
            except: pass
            
            with st.expander("البيانات التفصيلية"):
                st.dataframe(df, use_container_width=True)

    with tab_data_mgmt:
        st.markdown("#### 📂 استيراد البيانات المالية")
        st.info("يدعم النظام: ملفات PDF من تداول، ملفات Excel/CSV، ونسخ الجداول من TradingView/أرقام.")
        
        parser = FinancialParser()
        
        c_up, c_pst = st.columns(2)
        
        with c_up:
            uploaded_file = st.file_uploader("رفع ملف (PDF, Excel, CSV)", type=['pdf', 'xlsx', 'xls', 'csv'])
        
        with c_pst:
            pasted_text = st.text_area("أو الصق النص هنا", height=100)
            
        if st.button("🚀 معالجة البيانات"):
            with st.spinner("جاري التحليل الذكي..."):
                results, detected_symbol, err = parser.process_file_or_text(uploaded_file, pasted_text)
                
                if err:
                    st.error(err)
                elif not results:
                    st.warning("لم نتمكن من استخراج بيانات مفيدة. تأكد من صيغة الملف.")
                else:
                    st.success(f"تم استخراج {len(results)} سجلات!")
                    
                    # التحقق من الرمز
                    target_symbol = symbol
                    if detected_symbol and detected_symbol != symbol:
                        st.warning(f"⚠️ الملف يبدو أنه لشركة {detected_symbol}، وأنت في صفحة {symbol}.")
                        if st.checkbox(f"استخدام الرمز المكتشف ({detected_symbol})؟", value=True):
                            target_symbol = detected_symbol
                    
                    if not target_symbol:
                        target_symbol = st.text_input("لم نتمكن من تحديد الشركة، فضلاً أدخل الرمز (مثال: 1120.SR):")
                    
                    if target_symbol:
                        # عرض للمراجعة
                        preview = pd.DataFrame([{'Date': r['date'], **r['data']} for r in results])
                        st.write("مراجعة قبل الحفظ:")
                        st.dataframe(preview)
                        
                        if st.button("💾 حفظ في قاعدة البيانات"):
                            c = 0
                            for r in results:
                                if save_financial_record(target_symbol, r['date'], r['data'], 'Annual', 'FileImport'):
                                    c += 1
                            st.success(f"تم حفظ {c} سجلات لشركة {target_symbol}")
                            st.rerun()
