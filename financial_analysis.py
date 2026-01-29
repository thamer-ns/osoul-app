import pandas as pd
import streamlit as st
import io
import re
import pdfplumber
import yfinance as yf
from database import execute_query, fetch_table
from market_data import get_ticker_symbol

# ==============================================================
# 🧠 1. خوارزميات المعالجة الذكية (The Parsing Engine)
# ==============================================================

class FinancialParser:
    def __init__(self):
        # قاموس المصطلحات لربط النصوص العربية/الإنجليزية بقاعدة البيانات
        self.mapping = {
            'revenue': [
                r'إجمالي الإيرادات', r'مبيعات', r'sales', r'total revenue', r'revenues', 
                r'المبيعات', r'الإيرادات'
            ],
            'net_income': [
                r'صافي الدخل', r'صافي الربح', r'net income', r'profit', r'net profit',
                r'الربح \(الخسارة\) للفترة', r'ربح \(خسارة\) الفترة'
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
                r'cash from operating', r'التدفقات النقدية التشغيلية'
            ],
            'current_assets': [
                r'الموجودات المتداولة', r'إجمالي الموجودات المتداولة', r'current assets'
            ],
            'current_liabilities': [
                r'المطلوبات المتداولة', r'إجمالي المطلوبات المتداولة', r'current liabilities'
            ],
            'long_term_debt': [
                r'قروض طويلة الأجل', r'مطلوبات غير متداولة', r'long term debt', 
                r'non-current liabilities'
            ]
        }

    def _clean_number(self, val_str):
        """تحويل النصوص الرقمية المعقدة (1.5B, (500), 1,000) إلى أرقام"""
        if pd.isna(val_str): return 0.0
        s = str(val_str).strip().upper()
        
        # معامل الضرب (للمليارات والملايين)
        multiplier = 1.0
        if s.endswith('B') or 'مليار' in s: multiplier = 1_000_000_000
        elif s.endswith('M') or 'مليون' in s: multiplier = 1_000_000
        elif s.endswith('K') or 'ألف' in s: multiplier = 1_000
        
        # تنظيف الرموز
        s = re.sub(r'[^\d\.\-\(\)]', '', s)
        
        # معالجة الأقواس السالبة (500) -> -500
        if '(' in s and ')' in s:
            s = s.replace('(', '-').replace(')', '')
        
        try:
            return float(s) * multiplier
        except:
            return 0.0

    def _extract_symbol(self, text):
        """محاولة اكتشاف رمز الشركة من النص"""
        # البحث عن أنماط مثل: 4161, [1010], رمز 2222
        matches = re.findall(r'(?:رمز|كود|Symbol|Code)?\s*\[?(\d{4})\]?', text)
        for m in matches:
            if 1000 <= int(m) <= 9999: # نطاق الأسهم السعودية
                return f"{m}.SR"
        return None

    def _detect_format_and_parse(self, text):
        """تحديد نوع النص (تداول، TradingView، جدول بسيط)"""
        lines = text.split('\n')
        data_points = []
        
        # 1. نمط تداول (Tadawul/XBRL Style) - مثل ملف أسمنت ينبع
        if any("[300100]" in line or "قائمة المركز المالي" in line for line in lines):
            return self._parse_tadawul_style(lines)
            
        # 2. نمط TradingView / Web Table - مثل ملف بن داود
        if any("Total Revenue" in line or "إجمالي الإيرادات" in line for line in lines):
            return self._parse_web_table_style(lines)
            
        return [], None

    def _parse_tadawul_style(self, lines):
        """تحليل هيكلية ملفات تداول المعقدة"""
        extracted_data = {}
        dates = []
        current_section = ""
        symbol = None
        
        # البحث عن التواريخ والرمز أولاً
        for line in lines:
            if not symbol: symbol = self._extract_symbol(line)
            # محاولة التقاط التواريخ (YYYY-MM-DD)
            date_matches = re.findall(r'\d{4}-\d{2}-\d{2}', line)
            if date_matches and not dates:
                dates = sorted(date_matches, reverse=True) # الأحدث أولاً

        if not dates: dates = [pd.Timestamp.now().strftime('%Y-12-31')] # افتراضي

        # استخراج البيانات
        for line in lines:
            line = line.strip()
            # البحث عن القيم
            for key, patterns in self.mapping.items():
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        # استخراج الأرقام من السطر
                        nums = re.findall(r'-?[\d,]{2,}(?:\.\d+)?', line)
                        # تنظيف الأرقام
                        clean_nums = [self._clean_number(n) for n in nums]
                        
                        # تعيين القيم للتواريخ
                        for i, date_val in enumerate(dates):
                            if i < len(clean_nums):
                                if date_val not in extracted_data: extracted_data[date_val] = {}
                                # نأخذ القيمة فقط إذا لم تكن موجودة أو إذا كانت غير صفرية
                                if key not in extracted_data[date_val] or extracted_data[date_val][key] == 0:
                                    extracted_data[date_val][key] = clean_nums[i]
                        break 
        
        # تحويل للنسق النهائي
        results = []
        for d, data in extracted_data.items():
            results.append({'date': d, 'data': data})
            
        return results, symbol

    def _parse_web_table_style(self, lines):
        """تحليل جداول الويب المنسوخة (مثل TradingView)"""
        # محاولة تحويل النص إلى Dataframe
        try:
            # تنظيف الفواصل المكررة لجعلها Tab-separated افتراضياً
            clean_text = re.sub(r' {2,}', '\t', '\n'.join(lines))
            df = pd.read_csv(io.StringIO(clean_text), sep='\t', header=None, on_bad_lines='skip')
            
            # محاولة العثور على سطر التواريخ
            date_row_idx = -1
            for idx, row in df.iterrows():
                row_str = str(row.values)
                if re.search(r'20\d{2}', row_str): # سنة مثل 2021
                    date_row_idx = idx
                    break
            
            if date_row_idx == -1: return [], None

            dates = []
            # استخراج التواريخ من الأعمدة
            for col in df.iloc[date_row_idx]:
                d_match = re.search(r'20\d{2}', str(col))
                if d_match: dates.append(f"{d_match.group(0)}-12-31")
            
            results_map = {d: {} for d in dates}
            
            # المرور على الصفوف ومطابقة المفاتيح
            for idx, row in df.iterrows():
                if idx <= date_row_idx: continue
                row_label = str(row[0])
                
                for key, patterns in self.mapping.items():
                    if any(re.search(p, row_label, re.IGNORECASE) for p in patterns):
                        # لدينا تطابق، نأخذ القيم
                        values = row[1:].values
                        for i, val in enumerate(values):
                            if i < len(dates):
                                results_map[dates[i]][key] = self._clean_number(val)
            
            final_res = [{'date': d, 'data': data} for d, data in results_map.items() if data]
            
            # محاولة استخراج الرمز من أول بضعة أسطر
            symbol = self._extract_symbol('\n'.join(lines[:10]))
            
            return final_res, symbol

        except Exception as e:
            return [], None

    def process_file(self, uploaded_file):
        """معالجة الملفات المرفوعة (PDF, Excel, CSV)"""
        text = ""
        filename = uploaded_file.name.lower()
        
        try:
            if filename.endswith('.pdf'):
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        text += page.extract_text() + "\n"
                        # استخراج الجداول أيضاً
                        tables = page.extract_tables()
                        for table in tables:
                            for row in table:
                                text += "\t".join([str(c) for c in row if c]) + "\n"
                                
            elif filename.endswith(('.xlsx', '.xls', '.csv')):
                if filename.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                # تحويل الداتا فريم إلى نص منسق ليقرأه المعالج النصي
                text = df.to_string()
            
            return self._detect_format_and_parse(text)
            
        except Exception as e:
            return [], None

# ==============================================================
# 📥 2. وظائف التخزين (Database Interface)
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    try:
        # التأكد من وجود بيانات
        vals = {k: float(data.get(k, 0)) for k in [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'total_equity', 'operating_cash_flow', 'current_assets', 
            'current_liabilities', 'long_term_debt'
        ]}
        
        if sum(vals.values()) == 0: return False

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
        print(f"Save Error: {e}")
        return False

# ==============================================================
# 📊 3. الدوال المساعدة للواجهة (Helpers)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            required_cols = ['revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_equity', 'long_term_debt']
            for c in required_cols:
                if c not in df.columns: df[c] = 0.0
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    # (نفس الكود السابق للنسب المالية، لم يتغير)
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
        
        # Graham calculation logic kept intact
        try:
            t = yf.Ticker(get_ticker_symbol(symbol))
            eps = t.info.get('trailingEps')
            bvps = t.info.get('bookValue')
            if eps and bvps:
                product = 22.5 * eps * bvps
                metrics['Fair_Value_Graham'] = product ** 0.5 if product > 0 else 0.0
        except: pass

        if score >= 5: metrics['Financial_Health'] = "جيد / مستقر"
        else: metrics['Financial_Health'] = "هش / يحتاج مراجعة"
        metrics['Score'] = metrics['Piotroski_Score']
        metrics['Rating'] = metrics['Financial_Health']

        ops = []
        if curr.get('net_income',0) > prev.get('net_income',0): ops.append("نمو في الأرباح")
        if curr.get('operating_cash_flow',0) < 0: ops.append("تدفق نقدي سالب ⚠️")
        metrics['Opinions'] = " | ".join(ops)

    except: pass
    return metrics

# التوافق الخلفي
def get_fundamental_ratios(symbol):
    return get_advanced_fundamental_ratios(symbol)
