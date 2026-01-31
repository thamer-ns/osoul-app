# financial_analysis.py
import io
import re
import time
from datetime import datetime
from typing import Union, List, Dict, Any

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px

# استيراد الملفات المحلية (Core)
from database import execute_query, fetch_table
from market_data import get_ticker_symbol, fetch_price_from_yahoo
import data_source  # ✅ ضروري جداً لجلب الأسماء الصحيحة

# ---------------------------------------------------------
# 📦 المكتبات الاختيارية (PDF & Web)
# ---------------------------------------------------------
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


# ==============================================================
# 🧰 1. أدوات مساعدة (Helpers & Utilities)
# ==============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

def _safe_float(x: Any) -> float:
    """تحويل آمن لأي قيمة إلى رقم عشري"""
    try:
        if x is None: return 0.0
        if isinstance(x, (float, int, np.floating, np.integer)):
            return float(x)
        # تنظيف النص من الفواصل والرموز
        s = str(x).replace(",", "").replace(" ", "")
        # معالجة الأقواس السالبة (500) -> -500
        if "(" in s and ")" in s:
            s = s.replace("(", "-").replace(")", "")
        return float(s)
    except Exception:
        return 0.0

def _safe_date_str(d: Any) -> str:
    """تنسيق التاريخ إلى YYYY-MM-DD"""
    try:
        if hasattr(d, "strftime"):
            return d.strftime("%Y-%m-%d")
        s = str(d).strip()
        # معالجة 2024-12-31T00:00:00
        return s.split(" ")[0].split("T")[0]
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def _is_year_like(s: str) -> bool:
    """هل النص يشبه السنة (2020-2099)؟"""
    try:
        y = int(s)
        return 2000 <= y <= 2099
    except Exception:
        return False

def _looks_like_date_token(s: str) -> bool:
    s = str(s or "").strip()
    return bool(re.search(r"\b(20\d{2})\b", s) or re.search(r"\d{4}-\d{2}-\d{2}", s))


# ============================================================
# 🏗️ 2. FinancialAnalyzer Class (✅ الكلاس المصحح للواجهة)
# ============================================================
class FinancialAnalyzer:
    """
    كلاس مسؤول عن التحليل المالي وتوحيد التعامل مع بيانات الشركة.
    ✅ يحل مشكلة ظهور 'name' بدلاً من اسم الشركة الحقيقي.
    """
    def __init__(self, symbol: str):
        self.symbol = get_ticker_symbol(symbol)
        
        # ✅ الحل الجذري لمشكلة الاسم (معالجة القاموس)
        raw_info = data_source.get_company_details(symbol)
        
        if isinstance(raw_info, dict):
            self.name = raw_info.get('name', symbol)
            self.sector = raw_info.get('sector', 'Unknown')
        elif isinstance(raw_info, (list, tuple)) and len(raw_info) >= 2:
            self.name = raw_info[0]
            self.sector = raw_info[1]
        else:
            self.name = str(symbol)
            self.sector = 'Unknown'

    def get_basic_info(self):
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector
        }

    def analyze(self):
        """
        يقوم بتحليل سريع بناءً على البيانات المخزنة والسعر الحالي.
        """
        # جلب السعر الحالي
        market_info = fetch_price_from_yahoo(self.symbol)
        current_price = market_info.get("price", 0.0)

        # جلب البيانات المالية المخزنة (الأحدث أولاً)
        df = get_stored_financials_df(self.symbol, "Annual")
        
        metrics = {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "price": current_price,
            "pe_ratio": 0.0,
            "pb_ratio": 0.0,
            "dividend_yield": 0.0,
            "graham_value": 0.0,
            "recommendation": "Hold",
            "financial_health": "Unknown",
            "eps": 0.0,
            "bvps": 0.0,
            "roe": 0.0
        }

        if not df.empty:
            latest = df.iloc[0]
            # محاولة حساب EPS تقريبي من صافي الدخل (غير دقيق بدون عدد الأسهم)
            net_income = _safe_float(latest.get('net_income', 0))
            equity = _safe_float(latest.get('total_equity', 0))
            
            # محاولة جلب بيانات دقيقة من Yahoo Info
            eps = 0.0
            bvps = 0.0
            try:
                t = yf.Ticker(self.symbol)
                if t.info:
                    eps = t.info.get('trailingEps', 0.0)
                    bvps = t.info.get('bookValue', 0.0)
            except:
                pass

            metrics['eps'] = eps
            metrics['bvps'] = bvps

            # الحسابات
            if current_price > 0:
                if eps > 0: metrics["pe_ratio"] = round(current_price / eps, 2)
                if bvps > 0: metrics["pb_ratio"] = round(current_price / bvps, 2)
            
            # Graham Formula: Sqrt(22.5 * EPS * BVPS)
            if eps > 0 and bvps > 0:
                metrics["graham_value"] = round(np.sqrt(22.5 * eps * bvps), 2)

            # Health Check (Piotroski simplified integration)
            adv_ratios = get_advanced_fundamental_ratios(self.symbol)
            metrics["financial_health"] = adv_ratios.get("Financial_Health", "Unknown")

            # حساب العائد على حقوق الملكية ROE
            if equity > 0:
                metrics["roe"] = round((net_income / equity) * 100, 2)

        return metrics

# دالة مساعدة لاستخدام الكلاس بسهولة من الخارج
def get_stock_analysis(symbol):
    analyzer = FinancialAnalyzer(symbol)
    return analyzer.analyze()


# ==============================================================
# 🧠 3. FinancialParser (المحرك القوي لمعالجة النصوص)
# ==============================================================
class FinancialParser:
    """
    محلل نصوص متقدم يدعم:
    - ملفات PDF (باستخدام pdfplumber)
    - ملفات Excel/CSV
    - النصوص المنسوخة (Copy-Paste) من تداول، أرقام، TradingView
    """
    def __init__(self):
        # قاموس الأنماط (Regex Patterns) عربي وإنجليزي
        self.mapping = {
            "revenue": [
                r"إجمالي\s*الإيرادات", r"\bالمبيعات\b", r"\bsales\b",
                r"\btotal\s+revenue\b", r"\brevenues?\b", r"\brevenue\b",
            ],
            "net_income": [
                r"صافي\s*(الدخل|الربح)", r"\bnet\s+income\b", r"\bnet\s+profit\b",
                r"الربح\s*\(الخسارة\)\s*للفترة", r"صافي\s*الدخل\s*العائد",
            ],
            "total_assets": [
                r"إجمالي\s*(الموجودات|الأصول)", r"\btotal\s+assets\b", r"\bassets\b",
            ],
            "total_liabilities": [
                r"إجمالي\s*(المطلوبات|الالتزامات)", r"\btotal\s+liabilities\b", r"\bliabilities\b",
            ],
            "total_equity": [
                r"إجمالي\s*حقوق\s*الملكية", r"حقوق\s*(المساهمين|الملّاك)",
                r"\btotal\s+equity\b", r"\bshareholders?\s+equity\b",
            ],
            "operating_cash_flow": [
                r"صافي\s*التدفقات\s*النقدية\s*من\s*.*التشغيلية",
                r"\boperating\s+cash\s+flow\b", r"\bcash\s+from\s+operating\b",
                r"التدفقات\s*النقدية\s*التشغيلية", r"نقد\s*من\s*العمليات",
            ],
            "current_assets": [
                r"(إجمالي\s*)?الموجودات\s*المتداولة", r"\bcurrent\s+assets\b",
            ],
            "current_liabilities": [
                r"(إجمالي\s*)?المطلوبات\s*المتداولة", r"\bcurrent\s+liabilities\b",
            ],
            "long_term_debt": [
                r"قروض\s*طويلة\s*الأجل", r"\blong\s+term\s+debt\b",
                r"مطلوبات\s*غير\s*متداولة", r"\bnon[-\s]?current\s+liabilities\b",
            ],
        }
        # ترجمة الأنماط لزيادة السرعة
        self._compiled = {
            k: [re.compile(p, flags=re.IGNORECASE) for p in pats]
            for k, pats in self.mapping.items()
        }

    def _clean_number(self, val_str):
        """تنظيف الأرقام المعقدة (1.5B, (500), 1,000)"""
        if pd.isna(val_str):
            return 0.0

        s = str(val_str).strip().upper()

        # تحويل الأرقام العربية المشرقية
        arabic_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        s = s.translate(arabic_digits)

        multiplier = 1.0
        if "B" in s or "مليار" in s:
            multiplier = 1_000_000_000
        elif "M" in s or "مليون" in s:
            multiplier = 1_000_000
        elif "K" in s or "ألف" in s:
            multiplier = 1_000

        # إزالة الحروف والإبقاء على الأرقام والنقاط والأقواس والسالب
        s = re.sub(r"[^\d\.\-\(\)]", "", s)

        # الأقواس تعني سالب في المحاسبة
        if "(" in s and ")" in s:
            s = s.replace("(", "-").replace(")", "")

        try:
            val = float(s) * multiplier
            return val
        except Exception:
            return 0.0

    def _extract_symbol(self, text):
        """محاولة استخراج رمز الشركة (4 أرقام) من النص"""
        txt = str(text or "")
        matches = re.findall(r"\b([1-9]\d{3})\b", txt)
        for m in matches:
            if not m.startswith("20"):  # استبعاد السنوات
                return f"{m}.SR"
        return None

    def _detect_format_and_parse(self, text):
        lines = (text or "").split("\n")
        # فحص نمط تداول (يحتوي على [رمز])
        if any(re.search(r"\[\d{6}\]", line) for line in lines):
            return self._parse_tadawul_style(lines)
        # النمط الافتراضي (جدول)
        return self._parse_table_style(lines)

    def _parse_tadawul_style(self, lines):
        """تحليل النصوص المنسوخة من موقع تداول"""
        extracted_data = {}
        dates = []
        symbol = None

        # 1. البحث عن الرمز والتواريخ
        for line in lines:
            if not symbol:
                symbol = self._extract_symbol(line)
            dm = re.findall(r"(\d{4}-\d{2}-\d{2})", line)
            if dm and not dates:
                dates = sorted(list(set(dm)), reverse=True)[:4]

        # إذا لم نجد تواريخ صريحة، نبحث عن سنوات
        if not dates:
            for line in lines:
                years = re.findall(r"\b(20\d{2})\b", line)
                years = [y for y in years if _is_year_like(y)]
                if len(set(years)) >= 2:
                    dates = [f"{y}-12-31" for y in sorted(list(set(years)), reverse=True)[:4]]
                    break
        
        if not dates:
            dates = [datetime.now().strftime("%Y-12-31")]

        # 2. استخراج البيانات المالية
        for line in lines:
            line = (line or "").strip()
            if not line: continue

            for key, patterns in self._compiled.items():
                if any(p.search(line) for p in patterns):
                    # البحث عن الأرقام في السطر
                    nums = re.findall(r"(\(?-?[\d,]{2,}(?:\.\d+)?\)?)", line)
                    if not nums: continue

                    clean_nums = [self._clean_number(n) for n in nums]

                    # ربط الأرقام بالتواريخ
                    for i, d in enumerate(dates):
                        if i < len(clean_nums):
                            extracted_data.setdefault(d, {})
                            # نأخذ القيمة الأكبر (لتفادي الأصفار إذا تكرر السطر)
                            prev = extracted_data[d].get(key, 0.0)
                            if abs(clean_nums[i]) > abs(prev):
                                extracted_data[d][key] = clean_nums[i]
                    break

        results = [{"date": d, "data": data} for d, data in extracted_data.items()]
        return results, symbol

    def _parse_table_style(self, lines):
        """تحليل الجداول العامة (Excel / Copy-Paste)"""
        try:
            raw = "\n".join([str(x) for x in lines if str(x).strip()])
            if not raw.strip(): return [], None

            # محاولة تحويل النص إلى CSV-like
            clean_text = "\n".join([re.sub(r" {2,}|\t", ",", ln) for ln in raw.split("\n")])
            df = pd.read_csv(io.StringIO(clean_text), header=None, on_bad_lines="skip")

            date_row_idx = -1
            dates = []  # [(col_idx, date_str)]

            # البحث عن صف التواريخ
            for idx, row in df.iterrows():
                row_str = " ".join([str(x) for x in row.values])
                years = re.findall(r"\b(20\d{2})\b", row_str)
                years = [y for y in years if _is_year_like(y)]
                
                if len(set(years)) >= 2:
                    date_row_idx = idx
                    for col_idx, val in enumerate(row.values):
                        m = re.search(r"\b(20\d{2})\b", str(val))
                        if m: dates.append((col_idx, f"{m.group(1)}-12-31"))
                    break
                
                # تواريخ صريحة
                if re.search(r"\d{4}-\d{2}-\d{2}", row_str):
                    date_row_idx = idx
                    for col_idx, val in enumerate(row.values):
                        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(val))
                        if m: dates.append((col_idx, m.group(1)))
                    break

            if date_row_idx == -1:
                return [], self._extract_symbol("\n".join(lines[:10]))

            results_map = {}
            # قراءة البيانات تحت صف التاريخ
            for idx, row in df.iterrows():
                if idx <= date_row_idx: continue
                label = str(row.iloc[0]) if len(row) > 0 else ""
                
                for key, patterns in self._compiled.items():
                    if any(p.search(label) for p in patterns):
                        for col_idx, d in dates:
                            if col_idx < len(row):
                                v = self._clean_number(row.iloc[col_idx])
                                results_map.setdefault(d, {})
                                results_map[d][key] = v
                        break

            final_res = [{"date": d, "data": data} for d, data in results_map.items()]
            symbol = self._extract_symbol("\n".join(lines[:10]))
            return final_res, symbol

        except Exception as e:
            return [], None

    def process_file_or_text(self, uploaded_file=None, text_input=None):
        """الواجهة الرئيسية للمعالجة"""
        text = text_input or ""

        if uploaded_file:
            filename = (uploaded_file.name or "").lower()
            try:
                if filename.endswith(".pdf"):
                    if not pdfplumber:
                        return [], None, "⚠️ مكتبة pdfplumber غير مثبتة."
                    with pdfplumber.open(uploaded_file) as pdf:
                        for page in pdf.pages:
                            text += (page.extract_text() or "") + "\n"
                
                elif filename.endswith((".xlsx", ".xls")):
                    df = pd.read_excel(uploaded_file)
                    text = df.to_string(index=False)
                
                elif filename.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                    text = df.to_string(index=False)
            
            except Exception as e:
                return [], None, f"خطأ في قراءة الملف: {e}"

        if not text.strip():
            return [], None, "لا يوجد نص للمعالجة"

        results, symbol = self._detect_format_and_parse(text)
        return results, symbol, None


# ==============================================================
# 💾 4. Database Operations
# ==============================================================
def save_financial_record(symbol, date_str, data, period_type="Annual", source="Manual"):
    """حفظ البيانات المالية في قاعدة البيانات"""
    try:
        symbol = get_ticker_symbol(symbol)
        date_str = _safe_date_str(date_str)
        period_type = str(period_type or "Annual").strip().title()
        
        vals = {k: _safe_float(data.get(k, 0)) for k in [
            "revenue", "net_income", "total_assets", "total_liabilities", 
            "total_equity", "operating_cash_flow", "current_assets", 
            "current_liabilities", "long_term_debt"
        ]}

        if sum(abs(v) for v in vals.values()) == 0:
            return False

        query = """
            INSERT INTO financialstatements
            (symbol, date, period_type, source,
             revenue, net_income,
             total_assets, total_liabilities, total_equity,
             operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol, date, period_type)
            DO UPDATE SET
                revenue=EXCLUDED.revenue,
                net_income=EXCLUDED.net_income,
                total_assets=EXCLUDED.total_assets,
                total_liabilities=EXCLUDED.total_liabilities,
                total_equity=EXCLUDED.total_equity,
                operating_cash_flow=EXCLUDED.operating_cash_flow,
                current_assets=EXCLUDED.current_assets,
                current_liabilities=EXCLUDED.current_liabilities,
                long_term_debt=EXCLUDED.long_term_debt,
                source=EXCLUDED.source;
        """
        ok = execute_query(query, (
            symbol, date_str, period_type, source,
            vals["revenue"], vals["net_income"],
            vals["total_assets"], vals["total_liabilities"], vals["total_equity"],
            vals["operating_cash_flow"], vals["current_assets"], vals["current_liabilities"],
            vals["long_term_debt"]
        ))
        return bool(ok)
    except Exception as e:
        print(f"DB Error: {e}")
        return False

def get_stored_financials_df(symbol, period_type="Annual"):
    """جلب البيانات المالية كـ DataFrame"""
    try:
        symbol = get_ticker_symbol(symbol)
        period_type = str(period_type or "Annual").strip().title()

        df = fetch_table("financialstatements")
        if df is None or df.empty:
            return pd.DataFrame()

        if "symbol" in df.columns:
            df = df[df["symbol"].astype(str) == symbol]
        if "period_type" in df.columns:
            df = df[df["period_type"].astype(str).str.title() == period_type]

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            return df.sort_values("date", ascending=False)
        return df
    except Exception:
        return pd.DataFrame()


# ==============================================================
# 🌍 5. External Sources (Helpers)
# ==============================================================
def fetch_financials_from_yahoo(symbol: str) -> dict:
    # (تم الاحتفاظ بالكود الأصلي)
    sym = get_ticker_symbol(symbol)
    out = {}
    try:
        t = yf.Ticker(sym)
        fin = t.financials if hasattr(t, "financials") else pd.DataFrame()
        bs = t.balance_sheet if hasattr(t, "balance_sheet") else pd.DataFrame()
        cf = t.cashflow if hasattr(t, "cashflow") else pd.DataFrame()

        if fin is None: fin = pd.DataFrame()
        if bs is None: bs = pd.DataFrame()
        if cf is None: cf = pd.DataFrame()

        dates = sorted(list(set(fin.columns) | set(bs.columns) | set(cf.columns)), reverse=True)
        if not dates: return {}
        d = dates[0]

        def g(df, key):
            try:
                if df is None or df.empty: return 0.0
                if key in df.index and d in df.columns: return _safe_float(df.loc[key, d])
            except: pass
            return 0.0

        out = {
            "date": _safe_date_str(d),
            "revenue": g(fin, "Total Revenue"),
            "net_income": g(fin, "Net Income"),
            "total_assets": g(bs, "Total Assets"),
            "total_liabilities": g(bs, "Total Liabilities Net Minority Interest"),
            "total_equity": g(bs, "Total Equity Gross Minority Interest"),
            "operating_cash_flow": g(cf, "Operating Cash Flow"),
            "current_assets": g(bs, "Current Assets"),
            "current_liabilities": g(bs, "Current Liabilities"),
            "long_term_debt": g(bs, "Long Term Debt"),
        }
        return out
    except Exception:
        return {}

def _fetch_html(url: str, timeout=6) -> str:
    if not requests: return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200: return ""
        return r.text or ""
    except Exception:
        return ""

def fetch_financials_from_google_finance(symbol: str) -> dict:
    sym = get_ticker_symbol(symbol).replace(".SR", "")
    if not sym.isdigit(): return {}
    url = f"https://www.google.com/finance/quote/{sym}:TADAWUL"
    html = _fetch_html(url)
    if not html: return {}
    try:
        soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
        txt = soup.get_text("\n", strip=True) if soup else ""
    except: txt = ""
    if not txt.strip(): return {}
    
    parser = FinancialParser()
    results, detected = parser._detect_format_and_parse(txt)
    if not results: return {}
    
    results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
    rec = results[0]
    data = rec.get("data", {}) or {}
    data["date"] = rec.get("date")
    data["_source_url"] = url
    return data

def fetch_financials_from_argaam(symbol: str) -> dict:
    s = get_ticker_symbol(symbol).replace(".SR", "")
    if not s.isdigit(): return {}
    urls = [
        f"https://www.argaam.com/en/company/financials/{s}",
        f"https://www.argaam.com/ar/company/financials/{s}",
    ]
    for url in urls:
        html = _fetch_html(url, timeout=7)
        if not html: continue
        try:
            soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
            txt = soup.get_text("\n", strip=True) if soup else ""
        except: txt = ""
        if not txt.strip(): continue
        
        parser = FinancialParser()
        results, detected = parser._detect_format_and_parse(txt)
        if results:
            results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
            rec = results[0]
            data = rec.get("data", {}) or {}
            data["date"] = rec.get("date")
            data["_source_url"] = url
            return data
    return {}

def fetch_financials_from_investing(symbol: str) -> dict: return {}
def fetch_financials_from_tradingview(symbol: str) -> dict: return {}

def sync_auto_multi_sources(symbol: str, prefer="yahoo") -> tuple:
    symbol = get_ticker_symbol(symbol)
    sources = ["yahoo", "argaam", "google"] if prefer == "yahoo" else ["yahoo", "google", "argaam"]
    fetched = None
    for src in sources:
        if src == "yahoo": fetched = fetch_financials_from_yahoo(symbol)
        if src == "argaam": fetched = fetch_financials_from_argaam(symbol)
        if src == "google": fetched = fetch_financials_from_google_finance(symbol)
        if fetched: break
        
    if not fetched: return False, "فشل الجلب الآلي."
    
    d = fetched.get("date") or datetime.now().strftime("%Y-12-31")
    data = {k: fetched.get(k, 0) for k in [
        "revenue", "net_income", "total_assets", "total_liabilities", "total_equity",
        "operating_cash_flow", "current_assets", "current_liabilities", "long_term_debt"
    ]}
    ok = save_financial_record(symbol, d, data, "Annual", f"Auto_{str(src).title()}")
    return (ok, f"تم التحديث من {src}")

# ==============================================================
# ⚡ 6. Automation & Analysis Ratios
# ==============================================================
def sync_auto_yahoo(symbol):
    """تحديث آلي من Yahoo"""
    symbol = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(symbol)
        count = 0
        
        # دالة مساعدة لاستخراج البيانات
        def _process(fin, bs, cf, ptype):
            c = 0
            if fin is None: fin = pd.DataFrame()
            if bs is None: bs = pd.DataFrame()
            if cf is None: cf = pd.DataFrame()
            
            # توحيد الأعمدة (التواريخ)
            dates = sorted(list(set(fin.columns) | set(bs.columns) | set(cf.columns)), reverse=True)[:6]
            
            for d in dates:
                def g(df, k):
                    try: return _safe_float(df.loc[k, d]) if k in df.index else 0
                    except: return 0

                data = {
                    "revenue": g(fin, "Total Revenue") or g(fin, "Operating Revenue"),
                    "net_income": g(fin, "Net Income"),
                    "total_assets": g(bs, "Total Assets"),
                    "total_liabilities": g(bs, "Total Liabilities Net Minority Interest") or g(bs, "Total Liabilities"),
                    "total_equity": g(bs, "Total Equity Gross Minority Interest") or g(bs, "Stockholders Equity"),
                    "operating_cash_flow": g(cf, "Operating Cash Flow"),
                    "current_assets": g(bs, "Current Assets"),
                    "current_liabilities": g(bs, "Current Liabilities"),
                    "long_term_debt": g(bs, "Long Term Debt")
                }
                
                if save_financial_record(symbol, _safe_date_str(d), data, ptype, "Auto_Yahoo"):
                    c += 1
            return c

        count += _process(t.financials, t.balance_sheet, t.cashflow, "Annual")
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, "Quarterly")
        
        if count == 0:
            ok, msg = sync_auto_multi_sources(symbol)
            return ok, msg

        return True, f"تم تحديث {count} سجلات من Yahoo"
    except Exception as e:
        ok, msg = sync_auto_multi_sources(symbol)
        if ok: return True, f"فشل Yahoo وتم استخدام البديل: {msg}"
        return False, f"فشل التحديث: {str(e)}"

def get_advanced_fundamental_ratios(symbol):
    """حساب مؤشرات متقدمة (Piotroski, Graham)"""
    metrics = {
        "Fair_Value_Graham": 0.0,
        "Piotroski_Score": 0,
        "Financial_Health": "غير متوفر",
        "Score": 0,
        "Rating": "N/A",
        "Opinions": ""
    }

    symbol = get_ticker_symbol(symbol)
    df = get_stored_financials_df(symbol, "Annual")
    
    if df.empty or len(df) < 2:
        return metrics

    curr = df.iloc[0]
    prev = df.iloc[1]
    
    try:
        score = 0
        opinions = []
        
        # الربحية
        ni = _safe_float(curr.get("net_income", 0))
        ocf = _safe_float(curr.get("operating_cash_flow", 0))
        if ni > 0: score += 1
        if ocf > 0: score += 1
        if ocf > ni: 
            score += 1
            opinions.append("جودة أرباح عالية (كاش > صافي دخل)")
        
        # الرافعة المالية
        ltd_curr = _safe_float(curr.get("long_term_debt", 0))
        ltd_prev = _safe_float(prev.get("long_term_debt", 0))
        if ltd_curr < ltd_prev: score += 1
        
        # السيولة
        curr_ratio = _safe_float(curr.get("current_assets", 0)) / (_safe_float(curr.get("current_liabilities", 1)) or 1)
        prev_ratio = _safe_float(prev.get("current_assets", 0)) / (_safe_float(prev.get("current_liabilities", 1)) or 1)
        if curr_ratio > prev_ratio: score += 1

        metrics["Piotroski_Score"] = score
        if score >= 7: 
            metrics["Financial_Health"] = "قوي"
            metrics["Rating"] = "جيد"
        elif score <= 3: 
            metrics["Financial_Health"] = "ضعيف"
            metrics["Rating"] = "سيء"
        else: 
            metrics["Financial_Health"] = "متوسط"
            metrics["Rating"] = "متوسط"
        
        metrics["Score"] = score
        metrics["Opinions"] = " | ".join(opinions)
        
    except Exception:
        pass
        
    return metrics

def get_fundamental_ratios(symbol):
    return get_advanced_fundamental_ratios(symbol)

# ==============================================================
# 📝 7) Thesis & UI
# ==============================================================
def get_thesis(symbol):
    symbol = get_ticker_symbol(symbol)
    try:
        df = fetch_table("investmentthesis")
        if df is None or df.empty: return None
        sub = df[df["symbol"].astype(str) == symbol]
        return sub.iloc[0] if not sub.empty else None
    except: return None

def save_thesis(symbol, thesis_text, target_price, recommendation):
    symbol = get_ticker_symbol(symbol)
    today = datetime.now().strftime("%Y-%m-%d")
    execute_query(
        """
        INSERT INTO investmentthesis (symbol, thesis_text, target_price, recommendation, last_updated)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (symbol) DO UPDATE SET
            thesis_text=EXCLUDED.thesis_text,
            target_price=EXCLUDED.target_price,
            recommendation=EXCLUDED.recommendation,
            last_updated=EXCLUDED.last_updated;
        """,
        (symbol, thesis_text or "", _safe_float(target_price), recommendation or "Hold", today)
    )

def render_financial_dashboard_ui(symbol):
    # (تم الاحتفاظ بالدالة لواجهة المستخدم المستقلة)
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل", "⚙️ استيراد البيانات"])

    with tab_dashboard:
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, key=f"fin_ptype_{symbol}")
        df = get_stored_financials_df(symbol, ptype)
        if df.empty:
            st.warning("⚠️ لا توجد بيانات. قم بالتحديث أو الاستيراد.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("Piotroski Score", f"{metrics['Piotroski_Score']}/9", metrics["Financial_Health"])
            c2.metric("Graham Value", f"{metrics.get('Fair_Value_Graham', 0):,.2f}")
            c3.write(metrics.get("Opinions", ""))
            
            with st.expander("البيانات التفصيلية"):
                st.dataframe(df, use_container_width=True)

    with tab_data_mgmt:
        parser = FinancialParser()
        c_up, c_pst = st.columns(2)
        with c_up:
            uploaded_file = st.file_uploader("ملف (PDF, Excel, CSV)", type=["pdf", "xlsx", "csv"], key=f"up_{symbol}")
        with c_pst:
            pasted_text = st.text_area("أو الصق النص", height=100, key=f"paste_{symbol}")
        
        if st.button("تحديث آلي", key=f"sync_{symbol}"):
            ok, msg = sync_auto_yahoo(symbol)
            if ok: st.success(msg)
            else: st.error(msg)
            
        if st.button("معالجة الملف/النص", key=f"proc_{symbol}"):
            res, detected, err = parser.process_file_or_text(uploaded_file, pasted_text)
            if res:
                st.success(f"تم استخراج {len(res)} سجلات")
                st.dataframe(pd.DataFrame([{"Date": r["date"], **r["data"]} for r in res]))
                if st.button("حفظ", key=f"save_{symbol}"):
                    for r in res: save_financial_record(symbol, r["date"], r["data"], "Annual", "Manual")
                    st.success("تم الحفظ")
            else:
                st.error(err or "فشل الاستخراج")
