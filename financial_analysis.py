# financial_analysis.py
import io
import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px

# استيراد الملفات المحلية
from database import execute_query, fetch_table
from market_data import get_ticker_symbol, fetch_price_from_yahoo
import data_source  # ✅ ضروري جداً لجلب الأسماء الصحيحة

# PDF (اختياري)
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# Web (اختياري)
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


# ==============================================================
# 🧰 Helpers & Utilities
# ==============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

def _safe_float(x) -> float:
    try:
        if x is None: return 0.0
        if isinstance(x, (np.floating, np.integer, float, int)):
            return float(x)
        return float(str(x).replace(",", "").replace("(", "-").replace(")", "").strip())
    except Exception:
        return 0.0

def _safe_date_str(d) -> str:
    try:
        if hasattr(d, "strftime"): return d.strftime("%Y-%m-%d")
        s = str(d).strip().split(" ")[0].split("T")[0]
        return s
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def _is_year_like(s: str) -> bool:
    try:
        y = int(s)
        return 2000 <= y <= 2099
    except Exception:
        return False


# ============================================================
# 🏗️ FinancialAnalyzer Class (✅ الإضافة الجديدة لحل مشكلة الاسم)
# ============================================================
class FinancialAnalyzer:
    """
    كلاس مسؤول عن التحليل المالي وتوحيد التعامل مع بيانات الشركة.
    يحل مشكلة ظهور 'name' بدلاً من اسم الشركة الحقيقي.
    """
    def __init__(self, symbol):
        self.symbol = get_ticker_symbol(symbol)
        
        # ✅ الحل الجذري لمشكلة الاسم
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

        # جلب البيانات المالية المخزنة
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
            "financial_health": "Unknown"
        }

        if not df.empty:
            latest = df.iloc[0]
            eps = _safe_float(latest.get('net_income', 0)) / 1000000 # افتراضي بسيط، يفضل استخدام EPS حقيقي
            bvps = _safe_float(latest.get('total_equity', 0)) / 1000000 # افتراضي

            # محاولة استخدام Yahoo EPS إذا توفر لدقة أفضل
            try:
                t = yf.Ticker(self.symbol)
                if t.info:
                    eps = t.info.get('trailingEps', eps)
                    bvps = t.info.get('bookValue', bvps)
            except:
                pass

            # الحسابات
            if current_price > 0:
                if eps > 0: metrics["pe_ratio"] = round(current_price / eps, 2)
                if bvps > 0: metrics["pb_ratio"] = round(current_price / bvps, 2)
            
            # Graham
            if eps > 0 and bvps > 0:
                metrics["graham_value"] = round(np.sqrt(22.5 * eps * bvps), 2)

            # Health Check (Piotroski simplified integration)
            adv_ratios = get_advanced_fundamental_ratios(self.symbol)
            metrics["financial_health"] = adv_ratios.get("Financial_Health", "Unknown")

        return metrics

# دالة مساعدة لاستخدام الكلاس بسهولة
def get_stock_analysis(symbol):
    analyzer = FinancialAnalyzer(symbol)
    return analyzer.analyze()


# ==============================================================
# 🧠 FinancialParser (نظامك القديم القوي - تم الحفاظ عليه)
# ==============================================================
class FinancialParser:
    """
    يدعم استخراج البيانات من النصوص، PDF، والجداول المنسوخة.
    """
    def __init__(self):
        self.mapping = {
            "revenue": [r"إجمالي\s*الإيرادات", r"المبيعات", r"sales", r"revenue"],
            "net_income": [r"صافي\s*(الدخل|الربح)", r"net\s+income", r"profit"],
            "total_assets": [r"إجمالي\s*(الموجودات|الأصول)", r"total\s+assets"],
            "total_liabilities": [r"إجمالي\s*(المطلوبات|الالتزامات)", r"total\s+liabilities"],
            "total_equity": [r"حقوق\s*(المساهمين|الملكية)", r"total\s+equity"],
            "operating_cash_flow": [r"التدفقات\s*النقدية\s*التشغيلية", r"operating\s+cash\s+flow"],
            "current_assets": [r"الموجودات\s*المتداولة", r"current\s+assets"],
            "current_liabilities": [r"المطلوبات\s*المتداولة", r"current\s+liabilities"],
            "long_term_debt": [r"قروض\s*طويلة\s*الأجل", r"long\s+term\s+debt"],
        }
        self._compiled = {k: [re.compile(p, re.I) for p in v] for k, v in self.mapping.items()}

    def _clean_number(self, val_str):
        if pd.isna(val_str): return 0.0
        s = str(val_str).strip().upper()
        
        # تحويل الأرقام العربية
        s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        
        multiplier = 1.0
        if "B" in s or "مليار" in s: multiplier = 1e9
        elif "M" in s or "مليون" in s: multiplier = 1e6
        elif "K" in s or "ألف" in s: multiplier = 1e3
        
        # تنظيف
        s = re.sub(r"[^\d\.\-\(\)]", "", s)
        if "(" in s: s = s.replace("(", "-").replace(")", "")
        
        try:
            return float(s) * multiplier
        except:
            return 0.0

    def _extract_symbol(self, text):
        matches = re.findall(r"\b([1-9]\d{3})\b", str(text))
        for m in matches:
            if not m.startswith("20"): return f"{m}.SR"
        return None

    def _parse_tadawul_style(self, lines):
        # ... (نفس المنطق القديم الخاص بك لملفات تداول)
        extracted_data = {}
        dates = []
        symbol = None
        
        # محاولة إيجاد التواريخ
        for line in lines:
            if not symbol: symbol = self._extract_symbol(line)
            dm = re.findall(r"(\d{4}-\d{2}-\d{2})", line)
            if dm and not dates: dates = sorted(list(set(dm)), reverse=True)[:4]

        # إذا لم نجد تواريخ صريحة، نبحث عن سنوات
        if not dates:
             years = re.findall(r"\b(20\d{2})\b", " ".join(lines))
             years = sorted(list(set([y for y in years if _is_year_like(y)])), reverse=True)[:4]
             dates = [f"{y}-12-31" for y in years]

        if not dates: dates = [datetime.now().strftime("%Y-12-31")]

        for line in lines:
            if not line.strip(): continue
            for key, patterns in self._compiled.items():
                if any(p.search(line) for p in patterns):
                    nums = re.findall(r"(\(?-?[\d,]{2,}(?:\.\d+)?\)?)", line)
                    clean_nums = [self._clean_number(n) for n in nums]
                    for i, d in enumerate(dates):
                        if i < len(clean_nums):
                            extracted_data.setdefault(d, {})
                            extracted_data[d][key] = clean_nums[i]
                    break
                    
        return [{"date": d, "data": dt} for d, dt in extracted_data.items()], symbol

    def process_file_or_text(self, uploaded_file=None, text_input=None):
        text = text_input or ""
        if uploaded_file:
            try:
                if uploaded_file.name.endswith(".pdf") and pdfplumber:
                    with pdfplumber.open(uploaded_file) as pdf:
                        text = "\n".join([p.extract_text() or "" for p in pdf.pages])
                elif uploaded_file.name.endswith((".xlsx", ".csv")):
                    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith("x") else pd.read_csv(uploaded_file)
                    text = df.to_string()
            except Exception as e:
                return [], None, f"خطأ قراءة الملف: {e}"

        if not text.strip(): return [], None, "لا يوجد نص"
        
        # تبسيط: نستخدم منطق تداول لأنه الأقوى
        return self._parse_tadawul_style(text.split('\n'))


# ==============================================================
# 💾 DB Operations
# ==============================================================
def save_financial_record(symbol, date_str, data, period_type="Annual", source="Manual"):
    try:
        symbol = get_ticker_symbol(symbol)
        date_str = _safe_date_str(date_str)
        
        vals = {k: _safe_float(data.get(k, 0)) for k in [
            "revenue", "net_income", "total_assets", "total_liabilities", 
            "total_equity", "operating_cash_flow", "current_assets", 
            "current_liabilities", "long_term_debt"
        ]}
        
        if sum(abs(v) for v in vals.values()) == 0: return False

        query = """
            INSERT INTO financialstatements
            (symbol, date, period_type, source, revenue, net_income, total_assets, total_liabilities, total_equity, operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
            revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income, total_assets=EXCLUDED.total_assets,
            total_liabilities=EXCLUDED.total_liabilities, total_equity=EXCLUDED.total_equity,
            operating_cash_flow=EXCLUDED.operating_cash_flow, current_assets=EXCLUDED.current_assets,
            current_liabilities=EXCLUDED.current_liabilities, long_term_debt=EXCLUDED.long_term_debt,
            source=EXCLUDED.source;
        """
        execute_query(query, (symbol, date_str, period_type, source, *vals.values()))
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

def get_stored_financials_df(symbol, period_type="Annual"):
    try:
        symbol = get_ticker_symbol(symbol)
        df = fetch_table("financialstatements")
        if df.empty: return pd.DataFrame()
        
        df = df[df["symbol"].astype(str) == symbol]
        if "period_type" in df.columns:
            df = df[df["period_type"].str.lower() == period_type.lower()]
        
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date", ascending=False)
        return df
    except:
        return pd.DataFrame()

# ==============================================================
# ⚡ Automation & Ratios
# ==============================================================
def sync_auto_yahoo(symbol):
    symbol = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(symbol)
        count = 0
        
        for name, ptype in [(t.financials, "Annual"), (t.quarterly_financials, "Quarterly")]:
            if name is None or name.empty: continue
            
            # دمج البيانات من القوائم الثلاث
            # (هذا تبسيط، النسخة الكاملة تتطلب دمج balance_sheet و cashflow)
            # سنعتمد على الحفظ المباشر إذا وجدت بيانات
            for d in name.columns:
                data = {
                    "revenue": _safe_float(name.loc["Total Revenue", d]) if "Total Revenue" in name.index else 0,
                    "net_income": _safe_float(name.loc["Net Income", d]) if "Net Income" in name.index else 0,
                    # ... يمكن إضافة المزيد هنا
                }
                if save_financial_record(symbol, d, data, ptype, "Auto_Yahoo"):
                    count += 1
                    
        return True, f"تم تحديث {count} سجلات"
    except Exception as e:
        return False, str(e)

def get_advanced_fundamental_ratios(symbol):
    """
    حسابات Piotroski و Graham
    """
    metrics = {"Piotroski_Score": 0, "Financial_Health": "غير متوفر", "Fair_Value_Graham": 0.0}
    df = get_stored_financials_df(symbol, "Annual")
    if len(df) < 2: return metrics
    
    curr = df.iloc[0]
    
    # Piotroski (Simplified)
    score = 0
    if _safe_float(curr.get("net_income", 0)) > 0: score += 1
    if _safe_float(curr.get("operating_cash_flow", 0)) > 0: score += 1
    # ... بقية الشروط
    
    metrics["Piotroski_Score"] = score
    metrics["Financial_Health"] = "قوي" if score >= 7 else "ضعيف" if score <= 3 else "متوسط"
    
    return metrics
