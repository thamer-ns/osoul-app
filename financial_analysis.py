# financial_analysis.py
import io
import re
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px

from database import execute_query, fetch_table
from market_data import get_ticker_symbol

# ✅ Optional: use your nicer table renderer if available
try:
    from components import render_custom_table, safe_fmt
except Exception:
    render_custom_table = None
    safe_fmt = lambda x: str(x)

# PDF (اختياري)
try:
    import pdfplumber
except Exception:
    pdfplumber = None

# Web (اختياري)
try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None


# ==============================================================
# 🧰 Helpers
# ==============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _safe_float(x) -> float:
    try:
        if x is None:
            return 0.0
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        s = str(x).replace(",", "").strip()
        if s.lower() in ("nan", "none", ""):
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def _safe_div(a, b, default=0.0):
    try:
        a = _safe_float(a)
        b = _safe_float(b)
        if b == 0:
            return default
        return a / b
    except Exception:
        return default


def _safe_date_str(d) -> str:
    """
    يحاول تحويل تاريخ yahoo (Timestamp) أو string إلى YYYY-MM-DD
    """
    try:
        if hasattr(d, "strftime"):
            return d.strftime("%Y-%m-%d")
        s = str(d).strip()
        s = s.split(" ")[0]
        s = s.split("T")[0]
        return s
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _is_year_like(s: str) -> bool:
    try:
        y = int(s)
        return 2000 <= y <= 2099
    except Exception:
        return False


def _looks_like_date_token(s: str) -> bool:
    s = str(s or "").strip()
    return bool(re.search(r"\b(20\d{2})\b", s) or re.search(r"\d{4}-\d{2}-\d{2}", s))


def _fetch_html(url: str, timeout: int = 7) -> str:
    if not requests:
        return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return ""
        return r.text or ""
    except Exception:
        return ""


# ==============================================================
# ✅ Yahoo QuoteSummary JSON (Most stable for statements)
# ==============================================================
_YF_SESSION = None


def _yf_session():
    global _YF_SESSION
    if _YF_SESSION is None:
        if not requests:
            return None
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": HEADERS["User-Agent"],
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
                "Accept": "application/json,text/plain,*/*",
                "Connection": "keep-alive",
            }
        )
        _YF_SESSION = s
    return _YF_SESSION


def _http_get_json(url: str, timeout: int = 8, retries: int = 2, sleep: float = 0.6) -> dict:
    if not requests:
        return {}
    ses = _yf_session()
    if not ses:
        return {}
    for i in range(retries + 1):
        try:
            r = ses.get(url, timeout=timeout)
            if r.status_code == 200:
                try:
                    return r.json() or {}
                except Exception:
                    return {}
            if r.status_code in (429, 503):
                time.sleep(sleep * (2 if r.status_code == 429 else 1))
        except Exception:
            pass
        if i < retries:
            time.sleep(sleep)
    return {}


def _yf_raw(v, default=0.0) -> float:
    """
    Yahoo JSON often returns:
      {"raw": 123, "fmt": "..."}
    or None
    """
    try:
        if v is None:
            return float(default)
        if isinstance(v, dict):
            return float(v.get("raw", default) or default)
        return float(v)
    except Exception:
        return float(default)


def _yf_date_str(v) -> str:
    """
    endDate may be dict {"raw": 1703980800, "fmt": "2023-12-31"}
    """
    try:
        if isinstance(v, dict):
            if v.get("fmt"):
                return _safe_date_str(v["fmt"])
            raw = v.get("raw")
            if raw:
                return datetime.utcfromtimestamp(int(raw)).strftime("%Y-%m-%d")
        return _safe_date_str(v)
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _yahoo_quote_summary(symbol: str, modules: List[str]) -> dict:
    """
    Primary stable endpoint:
    https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=...
    """
    sym = get_ticker_symbol(symbol)
    if not sym:
        return {}
    mods = ",".join([m.strip() for m in modules if m and str(m).strip()])
    if not mods:
        return {}
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={mods}"
    return _http_get_json(url)


def _extract_stmt_list(root: dict, key: str) -> list:
    """
    Example keys:
      incomeStatementHistory -> {"incomeStatementHistory": [{"endDate":..., "totalRevenue":...}, ...]}
      incomeStatementHistoryQuarterly -> {"incomeStatementHistory": [...]}
    """
    try:
        rs = (root or {}).get("quoteSummary", {}).get("result", [])
        if not rs:
            return []
        obj = rs[0].get(key, {}) or {}
        for possible in ("incomeStatementHistory", "balanceSheetStatements", "cashflowStatements"):
            if possible in obj and isinstance(obj[possible], list):
                return obj[possible]
        for _, v in obj.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    except Exception:
        pass
    return []


def _normalize_yahoo_statements(symbol: str, frequency: str = "Annual") -> List[Dict[str, Any]]:
    """
    frequency: "Annual" or "Quarterly"
    returns list of records:
      [{"date": "YYYY-MM-DD", "data": {...}}, ...]
    """
    freq = str(frequency or "Annual").strip().title()
    if freq not in ("Annual", "Quarterly"):
        freq = "Annual"

    modules = [
        "incomeStatementHistory",
        "incomeStatementHistoryQuarterly",
        "balanceSheetHistory",
        "balanceSheetHistoryQuarterly",
        "cashflowStatementHistory",
        "cashflowStatementHistoryQuarterly",
    ]
    root = _yahoo_quote_summary(symbol, modules)
    if not root:
        return []

    is_key = "incomeStatementHistoryQuarterly" if freq == "Quarterly" else "incomeStatementHistory"
    bs_key = "balanceSheetHistoryQuarterly" if freq == "Quarterly" else "balanceSheetHistory"
    cf_key = "cashflowStatementHistoryQuarterly" if freq == "Quarterly" else "cashflowStatementHistory"

    income_list = _extract_stmt_list(root, is_key)
    bs_list = _extract_stmt_list(root, bs_key)
    cf_list = _extract_stmt_list(root, cf_key)

    by_date: Dict[str, Dict[str, Any]] = {}

    def upsert(rec: dict, kind: str):
        if not isinstance(rec, dict):
            return
        d = _yf_date_str(rec.get("endDate") or rec.get("asOfDate") or rec.get("periodEndDate"))
        if not d:
            return
        by_date.setdefault(d, {})
        by_date[d][kind] = rec

    for r in income_list:
        upsert(r, "is")
    for r in bs_list:
        upsert(r, "bs")
    for r in cf_list:
        upsert(r, "cf")

    if not by_date:
        return []

    def g(dct: dict, *keys, default=0.0) -> float:
        for k in keys:
            if k in dct:
                return _yf_raw(dct.get(k), default=default)
        return float(default)

    out: List[Dict[str, Any]] = []
    for d in sorted(by_date.keys(), reverse=True):
        isr = by_date[d].get("is", {}) or {}
        bsr = by_date[d].get("bs", {}) or {}
        cfr = by_date[d].get("cf", {}) or {}

        data = {
            "revenue": g(isr, "totalRevenue", "revenue", "totalOperatingRevenue", default=0.0),
            "net_income": g(
                isr,
                "netIncome",
                "netIncomeCommonStockholders",
                "netIncomeApplicableToCommonShares",
                default=0.0,
            ),
            "total_assets": g(bsr, "totalAssets", default=0.0),
            "total_liabilities": g(
                bsr,
                "totalLiab",
                "totalLiabilitiesNetMinorityInterest",
                "totalLiabilities",
                default=0.0,
            ),
            "total_equity": g(
                bsr,
                "totalStockholderEquity",
                "totalEquityGrossMinorityInterest",
                "totalEquity",
                default=0.0,
            ),
            "operating_cash_flow": g(cfr, "totalCashFromOperatingActivities", "operatingCashflow", default=0.0),
            "current_assets": g(bsr, "totalCurrentAssets", "currentAssets", default=0.0),
            "current_liabilities": g(bsr, "totalCurrentLiabilities", "currentLiabilities", default=0.0),
            "long_term_debt": g(
                bsr,
                "longTermDebt",
                "longTermDebtNoncurrent",
                "longTermDebtAndCapitalLeaseObligation",
                default=0.0,
            ),
        }

        if sum(abs(_safe_float(v)) for v in data.values()) == 0:
            continue

        out.append({"date": d, "data": data})

    return out


def fetch_financial_statements_yahoo_json(symbol: str, period_type: str = "Annual") -> List[Dict[str, Any]]:
    """
    Returns list of {"date":..., "data":...}
    period_type: Annual / Quarterly
    """
    try:
        return _normalize_yahoo_statements(symbol, frequency=period_type)
    except Exception:
        return []


# ==============================================================
# 🧠 1) FinancialParser
# ==============================================================
class FinancialParser:
    """
    - يدعم PDF تداول
    - يدعم Excel/CSV نصي
    - يدعم Copy/Paste من المتصفح (TradingView / أرقام / Investing / Google Finance)
    """

    def __init__(self):
        self.mapping = {
            "revenue": [
                r"إجمالي\s*الإيرادات",
                r"\bالمبيعات\b",
                r"\bsales\b",
                r"\btotal\s+revenue\b",
                r"\brevenues?\b",
                r"\brevenue\b",
            ],
            "net_income": [
                r"صافي\s*(الدخل|الربح)",
                r"\bnet\s+income\b",
                r"\bnet\s+profit\b",
                r"الربح\s*\(الخسارة\)\s*للفترة",
                r"صافي\s*الدخل\s*العائد",
            ],
            "total_assets": [
                r"إجمالي\s*(الموجودات|الأصول)",
                r"\btotal\s+assets\b",
                r"\bassets\b",
            ],
            "total_liabilities": [
                r"إجمالي\s*(المطلوبات|الالتزامات)",
                r"\btotal\s+liabilities\b",
                r"\bliabilities\b",
            ],
            "total_equity": [
                r"إجمالي\s*حقوق\s*الملكية",
                r"حقوق\s*(المساهمين|الملّاك)",
                r"\btotal\s+equity\b",
                r"\bshareholders?\s+equity\b",
            ],
            "operating_cash_flow": [
                r"صافي\s*التدفقات\s*النقدية\s*من\s*.*التشغيلية",
                r"\boperating\s+cash\s+flow\b",
                r"\bcash\s+from\s+operating\b",
                r"التدفقات\s*النقدية\s*التشغيلية",
                r"نقد\s*من\s*العمليات",
            ],
            "current_assets": [
                r"(إجمالي\s*)?الموجودات\s*المتداولة",
                r"\bcurrent\s+assets\b",
            ],
            "current_liabilities": [
                r"(إجمالي\s*)?المطلوبات\s*المتداولة",
                r"\bcurrent\s+liabilities\b",
            ],
            "long_term_debt": [
                r"قروض\s*طويلة\s*الأجل",
                r"\blong\s+term\s+debt\b",
                r"مطلوبات\s*غير\s*متداولة",
                r"\bnon[-\s]?current\s+liabilities\b",
            ],
        }

        self._compiled = {k: [re.compile(p, flags=re.IGNORECASE) for p in pats] for k, pats in self.mapping.items()}

    def _clean_number(self, val_str):
        if pd.isna(val_str):
            return 0.0

        s = str(val_str).strip().upper()

        arabic_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        s = s.translate(arabic_digits)

        multiplier = 1.0
        if s.endswith("B") or "مليار" in s:
            multiplier = 1_000_000_000
        elif s.endswith("M") or "مليون" in s:
            multiplier = 1_000_000
        elif s.endswith("K") or "ألف" in s:
            multiplier = 1_000

        s = re.sub(r"[^\d\.\-\(\)]", "", s)

        if "(" in s and ")" in s:
            s = s.replace("(", "-").replace(")", "")

        try:
            return float(s) * multiplier
        except Exception:
            return 0.0

    def _extract_symbol(self, text):
        txt = str(text or "")
        matches = re.findall(r"\b([1-9]\d{3})\b", txt)
        for m in matches:
            if not m.startswith("20"):
                return f"{m}.SR"
        return None

    def _detect_format_and_parse(self, text):
        lines = (text or "").split("\n")

        if any(re.search(r"\[\d{6}\]", line) for line in lines):
            return self._parse_tadawul_style(lines)

        return self._parse_table_style(lines)

    def _parse_tadawul_style(self, lines):
        extracted_data = {}
        dates = []
        symbol = None

        for line in lines:
            if not symbol:
                symbol = self._extract_symbol(line)

            dm = re.findall(r"(\d{4}-\d{2}-\d{2})", line)
            if dm and not dates:
                dates = sorted(list(set(dm)), reverse=True)[:4]

        if not dates:
            for line in lines:
                years = re.findall(r"\b(20\d{2})\b", line)
                years = [y for y in years if _is_year_like(y)]
                if len(set(years)) >= 2:
                    dates = [f"{y}-12-31" for y in sorted(list(set(years)), reverse=True)[:4]]
                    break

        if not dates:
            dates = [datetime.now().strftime("%Y-12-31")]

        for line in lines:
            line = (line or "").strip()
            if not line:
                continue

            for key, patterns in self._compiled.items():
                if any(p.search(line) for p in patterns):
                    nums = re.findall(r"(\(?-?[\d,]{2,}(?:\.\d+)?\)?)", line)
                    if not nums:
                        continue

                    clean_nums = [self._clean_number(n) for n in nums]

                    for i, d in enumerate(dates):
                        if i < len(clean_nums):
                            extracted_data.setdefault(d, {})
                            prev = extracted_data[d].get(key, 0.0)
                            if abs(clean_nums[i]) > abs(prev):
                                extracted_data[d][key] = clean_nums[i]
                    break

        results = [{"date": d, "data": data} for d, data in extracted_data.items()]
        return results, symbol

    def _parse_table_style(self, lines):
        try:
            raw = "\n".join([str(x) for x in lines if str(x).strip()])
            if not raw.strip():
                return [], None

            clean_text = "\n".join([re.sub(r" {2,}|\t", ",", ln) for ln in raw.split("\n")])
            df = pd.read_csv(io.StringIO(clean_text), header=None, on_bad_lines="skip")

            date_row_idx = -1
            dates = []
            for idx, row in df.iterrows():
                row_vals = [str(x) for x in row.values if str(x).strip() != "nan"]
                row_str = " ".join(row_vals)

                years = re.findall(r"\b(20\d{2})\b", row_str)
                years = [y for y in years if _is_year_like(y)]
                if len(set(years)) >= 2:
                    date_row_idx = idx
                    for col_idx, val in enumerate(row.values):
                        s = str(val)
                        m = re.search(r"\b(20\d{2})\b", s)
                        if m:
                            dates.append((col_idx, f"{m.group(1)}-12-31"))
                    break

                if re.search(r"\d{4}-\d{2}-\d{2}", row_str):
                    date_row_idx = idx
                    for col_idx, val in enumerate(row.values):
                        s = str(val)
                        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
                        if m:
                            dates.append((col_idx, m.group(1)))
                    break

            if date_row_idx == -1 or not dates:
                return [], self._extract_symbol("\n".join(lines[:10]))

            results_map = {}

            for idx, row in df.iterrows():
                if idx <= date_row_idx:
                    continue
                label = str(row.iloc[0]) if len(row) else ""
                if not label or label == "nan":
                    continue

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
            print(f"Parsing Error: {e}")
            return [], None

    def process_file_or_text(self, uploaded_file=None, text_input=None):
        text = ""

        if text_input:
            text = text_input

        elif uploaded_file:
            filename = (uploaded_file.name or "").lower()
            try:
                if filename.endswith(".pdf"):
                    if not pdfplumber:
                        return [], None, "مكتبة pdfplumber غير مثبتة."
                    with pdfplumber.open(uploaded_file) as pdf:
                        for page in pdf.pages:
                            t = page.extract_text() or ""
                            text += t + "\n"

                elif filename.endswith((".xlsx", ".xls")):
                    df = pd.read_excel(uploaded_file)
                    text = df.to_string(index=False)

                elif filename.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                    text = df.to_string(index=False)

                else:
                    return [], None, "صيغة الملف غير مدعومة."

            except Exception as e:
                return [], None, f"خطأ في قراءة الملف: {e}"

        if not text.strip():
            return [], None, "لا يوجد نص للمعالجة"

        results, symbol = self._detect_format_and_parse(text)
        return results, symbol, None


# ==============================================================
# 💾 2) DB Save / Fetch
# ==============================================================
def save_financial_record(symbol, date_str, data, period_type="Annual", source="Manual"):
    """
    ✅ إصلاح أسماء الجداول:
    - financialstatements (lowercase) بدون quotes
    """
    try:
        symbol = get_ticker_symbol(symbol)
        date_str = _safe_date_str(date_str)
        period_type = str(period_type or "Annual").strip().title()
        source = str(source or "Manual").strip()[:30]

        keys = [
            "revenue",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "operating_cash_flow",
            "current_assets",
            "current_liabilities",
            "long_term_debt",
        ]

        vals = {k: _safe_float((data or {}).get(k, 0)) for k in keys}

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

        ok = execute_query(
            query,
            (
                symbol,
                date_str,
                period_type,
                source,
                vals["revenue"],
                vals["net_income"],
                vals["total_assets"],
                vals["total_liabilities"],
                vals["total_equity"],
                vals["operating_cash_flow"],
                vals["current_assets"],
                vals["current_liabilities"],
                vals["long_term_debt"],
            ),
        )
        return bool(ok)
    except Exception as e:
        print(f"DB Error: {e}")
        return False


def get_stored_financials_df(symbol, period_type="Annual"):
    """
    ✅ يرجع DataFrame من financialstatements
    """
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

        return df.sort_values("date", ascending=False) if "date" in df.columns else df
    except Exception:
        return pd.DataFrame()


# ==============================================================
# 🌍 3) External Sources (best-effort, safe)
# ==============================================================

def fetch_financials_from_google_finance(symbol: str) -> dict:
    """
    Best-effort parsing from Google Finance text -> FinancialParser.
    قد تتغير الصفحة لذلك نعتبره احتياطي فقط.
    """
    try:
        sym = get_ticker_symbol(symbol).replace(".SR", "")
        if not sym.isdigit():
            return {}

        url = f"https://www.google.com/finance/quote/{sym}:TADAWUL"
        html = _fetch_html(url, timeout=7)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
        txt = soup.get_text("\n", strip=True) if soup else ""
        if not txt.strip():
            return {}

        parser = FinancialParser()
        results, _ = parser._detect_format_and_parse(txt)
        if not results:
            return {}

        results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
        rec = results[0]
        data = rec.get("data", {}) or {}
        data["date"] = rec.get("date")
        data["_source_url"] = url
        return data
    except Exception:
        return {}


def fetch_financials_from_argaam(symbol: str) -> dict:
    """
    Best-effort parsing from Argaam text -> FinancialParser.
    قد تتغير الصفحة لذلك نعتبره احتياطي فقط.
    """
    s = get_ticker_symbol(symbol).replace(".SR", "")
    if not s.isdigit():
        return {}

    urls = [
        f"https://www.argaam.com/en/company/financials/{s}",
        f"https://www.argaam.com/ar/company/financials/{s}",
        f"https://www.argaam.com/en/company/stock/overview/{s}",
        f"https://www.argaam.com/ar/company/stock/overview/{s}",
    ]

    for url in urls:
        try:
            html = _fetch_html(url, timeout=8)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
            txt = soup.get_text("\n", strip=True) if soup else ""
            if not txt.strip():
                continue

            parser = FinancialParser()
            results, _ = parser._detect_format_and_parse(txt)
            if not results:
                continue

            results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
            rec = results[0]
            data = rec.get("data", {}) or {}
            data["date"] = rec.get("date")
            data["_source_url"] = url
            return data
        except Exception:
            continue

    return {}


def fetch_financials_from_yahoo(symbol: str) -> dict:
    """
    ✅ يجلب من Yahoo JSON (quoteSummary) بدل yfinance.financials
    يرجع أحدث سجل Annual.
    """
    sym = get_ticker_symbol(symbol)
    try:
        recs = fetch_financial_statements_yahoo_json(sym, "Annual")
        if not recs:
            return {}
        recs = sorted(recs, key=lambda x: x.get("date", ""), reverse=True)
        top = recs[0]
        data = top.get("data", {}) or {}
        data["date"] = top.get("date")
        return data
    except Exception:
        return {}


# ==============================================================
# ✅ Unified Financial Statements (DB cache + Yahoo JSON + fallback)
# ==============================================================
@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)  # 6 hours
def get_financial_statements(symbol: str, period_type: str = "Annual", refresh: bool = False) -> pd.DataFrame:
    """
    يرجع DataFrame موحّد من جدول financialstatements.
    - لو refresh=False: يرجع المخزن إن وجد (سريع)
    - لو refresh=True أو لا يوجد مخزن: يحاول Yahoo JSON ثم بدائل
    """
    sym = get_ticker_symbol(symbol)
    ptype = str(period_type or "Annual").strip().title()
    if ptype not in ("Annual", "Quarterly"):
        ptype = "Annual"

    stored = get_stored_financials_df(sym, ptype)

    if (not refresh) and (stored is not None) and (not stored.empty):
        return stored

    records = fetch_financial_statements_yahoo_json(sym, ptype)

    if not records and ptype == "Annual":
        try:
            d = fetch_financials_from_argaam(sym) or {}
            if d:
                records = [{"date": d.get("date") or datetime.now().strftime("%Y-12-31"), "data": d}]
        except Exception:
            pass

    if not records and ptype == "Annual":
        try:
            d2 = fetch_financials_from_google_finance(sym) or {}
            if d2:
                records = [{"date": d2.get("date") or datetime.now().strftime("%Y-12-31"), "data": d2}]
        except Exception:
            pass

    if records:
        for rec in records:
            d = rec.get("date")
            data = rec.get("data", {}) or {}
            save_financial_record(
                sym,
                d,
                data,
                period_type=ptype,
                source="YahooJSON" if isinstance(data, dict) and "revenue" in data else "External",
            )
        return get_stored_financials_df(sym, ptype)

    return stored if stored is not None else pd.DataFrame()


# ==============================================================
# 🧩 Fallback Sync (بديل آمن لـ sync_auto_multi_sources)
# ==============================================================
def sync_auto_multi_sources(symbol: str, prefer: str = "yahoo") -> Tuple[bool, str]:
    """
    بديل آمن إذا فشل Yahoo:
    - يحاول Argaam ثم Google Finance (إن توفر requests/bs4)
    - يحفظ سجل Annual واحد على الأقل
    """
    symbol = get_ticker_symbol(symbol)
    saved = 0
    notes: List[str] = []

    try:
        d = fetch_financials_from_argaam(symbol) or {}
        if isinstance(d, dict) and d:
            dt = d.get("date") or datetime.now().strftime("%Y-12-31")
            if save_financial_record(symbol, dt, d, "Annual", "Argaam"):
                saved += 1
                notes.append("تمت المحاولة من أرقام")
    except Exception as e:
        notes.append(f"أرقام فشل: {e}")

    if saved == 0:
        try:
            d2 = fetch_financials_from_google_finance(symbol) or {}
            if isinstance(d2, dict) and d2:
                dt = d2.get("date") or datetime.now().strftime("%Y-12-31")
                if save_financial_record(symbol, dt, d2, "Annual", "GoogleFinance"):
                    saved += 1
                    notes.append("تمت المحاولة من Google Finance")
        except Exception as e:
            notes.append(f"Google Finance فشل: {e}")

    if saved > 0:
        return True, f"تم حفظ {saved} سجل من بدائل Yahoo. " + " | ".join(notes)
    return False, "لم تنجح البدائل. " + " | ".join(notes)


# ==============================================================
# ⚡ 4) Yahoo Sync (used by views.py)
# ==============================================================
def sync_auto_yahoo(symbol):
    """
    ✅ نفس اسم الدالة لتوافق views.py
    - يحفظ Annual + Quarterly (آخر 6 تواريخ) من yfinance
    - إذا فشل: يستخدم sync_auto_multi_sources
    """
    symbol = get_ticker_symbol(symbol)
    try:
        t = yf.Ticker(symbol)

        def _process(fin, bs, cf, p_type: str):
            if fin is None:
                fin = pd.DataFrame()
            if bs is None:
                bs = pd.DataFrame()
            if cf is None:
                cf = pd.DataFrame()

            if fin.empty and bs.empty and cf.empty:
                return 0

            dates = sorted(list(set(fin.columns) | set(bs.columns) | set(cf.columns)), reverse=True)[:6]
            if not dates:
                return 0

            def g(df, k, d):
                try:
                    if df is None or df.empty:
                        return 0.0
                    if k in df.index and d in df.columns:
                        return _safe_float(df.loc[k, d])
                except Exception:
                    return 0.0
                return 0.0

            c = 0
            for d in dates:
                d_str = _safe_date_str(d)

                data = {
                    "revenue": g(fin, "Total Revenue", d) or g(fin, "Operating Revenue", d),
                    "net_income": g(fin, "Net Income", d),
                    "total_assets": g(bs, "Total Assets", d),
                    "total_liabilities": (g(bs, "Total Liabilities Net Minority Interest", d) or g(bs, "Total Liabilities", d)),
                    "total_equity": (
                        g(bs, "Total Equity Gross Minority Interest", d)
                        or g(bs, "Total Stockholder Equity", d)
                        or g(bs, "Stockholders Equity", d)
                    ),
                    "operating_cash_flow": g(cf, "Operating Cash Flow", d),
                    "current_assets": g(bs, "Current Assets", d),
                    "current_liabilities": g(bs, "Current Liabilities", d),
                    "long_term_debt": g(bs, "Long Term Debt", d),
                }

                if save_financial_record(symbol, d_str, data, p_type, "Auto_Yahoo"):
                    c += 1

            return c

        count = 0
        count += _process(t.financials, t.balance_sheet, t.cashflow, "Annual")
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, "Quarterly")

        if count == 0:
            ok2, msg2 = sync_auto_multi_sources(symbol, prefer="yahoo")
            if ok2:
                return True, f"Yahoo لم يعطِ بيانات كافية. {msg2}"
            return False, "Yahoo لم يعطِ بيانات، ولم تنجح البدائل."

        return True, f"تم تحديث {count} سجلات من Yahoo"

    except Exception as e:
        ok2, msg2 = sync_auto_multi_sources(symbol, prefer="yahoo")
        if ok2:
            return True, f"تعذر Yahoo. {msg2}"
        return False, str(e)


# ==============================================================
# 📐 5) Fundamental Ratios (Piotroski + Graham + Advanced Pack)
# ==============================================================
def _fetch_yahoo_info(symbol: str) -> dict:
    try:
        t = yf.Ticker(symbol)
        info = getattr(t, "info", {}) or {}
        if not isinstance(info, dict):
            return {}
        return info
    except Exception:
        return {}

# --- (باقي الدوال كما هي بدون تغيير) ---
# ملاحظة: هنا نترك بقية الملف كما هو عندك من "compute_dupont" إلى نهاية render_financial_dashboard_ui
# لكن سنعدل فقط أماكن عرض الجداول في UI لإرجاع الشكل الجميل.

# ==============================================================
# 🖥️ (Optional) Standalone UI (not required by views.py)
# ==============================================================
def _render_df_pretty(df: pd.DataFrame, title: str = ""):
    if title:
        st.markdown(f"**{title}**")

    if df is None or df.empty:
        st.info("لا توجد بيانات.")
        return

    # Use your custom table if available
    if callable(render_custom_table):
        # Best-effort: auto columns mapping
        cols = []
        for c in df.columns:
            typ = "number"
            lc = str(c).lower()
            if "date" in lc:
                typ = "date"
            elif any(k in lc for k in ["amount", "revenue", "income", "cash", "assets", "liabilities", "equity", "debt", "price", "value"]):
                typ = "money"
            cols.append((c, str(c), typ))
        try:
            render_custom_table(df, cols)
            return
        except Exception:
            pass

    st.dataframe(df, use_container_width=True)


def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ استيراد البيانات"])

    with tab_dashboard:
        ptype = st.radio(
            "نطاق التحليل:",
            ["Annual", "Quarterly"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"fin_ptype_inline_{symbol}",
        )
        df = get_stored_financials_df(symbol, ptype)

        if df.empty:
            st.warning("⚠️ لا توجد بيانات. استخدم تبويب الاستيراد أو التحديث الآلي.")
        else:
            metrics = get_fundamental_ratios(symbol)

            c1, c2, c3 = st.columns(3)
            c1.metric("F-Score", f"{int(_safe_float(metrics.get('Piotroski_Score',0)))}/9", str(metrics.get("Financial_Health","")))
            c2.metric(
                "Graham Value",
                f"{_safe_float(metrics.get('Fair_Value_Graham', 0)):,.2f}" if _safe_float(metrics.get("Fair_Value_Graham",0)) else "N/A",
            )
            c3.write(str(metrics.get("Opinions", "")))

            try:
                plot_df = df.copy()
                if "date" in plot_df.columns:
                    plot_df["Year"] = plot_df["date"].dt.strftime("%Y-%m")
                cols = [c for c in ["revenue", "net_income", "operating_cash_flow"] if c in plot_df.columns]
                if cols:
                    fig = px.bar(plot_df.sort_values("date"), x="Year", y=cols, barmode="group")
                    st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

            with st.expander("البيانات التفصيلية"):
                _render_df_pretty(df, "")

            with st.expander("📌 مؤشرات متقدمة (DuPont / Altman / Valuation / SGR)"):
                try:
                    st.json({
                        "ROE": metrics.get("ROE", 0),
                        "ROA": metrics.get("ROA", 0),
                        "DuPont PM": metrics.get("DuPont_Profit_Margin", 0),
                        "DuPont AT": metrics.get("DuPont_Asset_Turnover", 0),
                        "DuPont EM": metrics.get("DuPont_Equity_Multiplier", 0),
                        "Altman Z": metrics.get("Altman_Z", 0),
                        "SGR": metrics.get("SGR", 0),
                        "CR": metrics.get("Current_Ratio", 0),
                        "OCF/NI": metrics.get("OCF_to_NetIncome", 0),
                        "PE": metrics.get("PE_Trailing", 0),
                        "PEG": metrics.get("PEG", 0),
                        "P/B": metrics.get("PB", 0),
                    })
                except Exception:
                    pass

    with tab_data_mgmt:
        st.info("يدعم: PDF تداول / Excel/CSV / Copy-Paste من المتصفح (TradingView/أرقام/Investing/Google Finance)")
        parser = FinancialParser()

        c_up, c_pst = st.columns(2)
        with c_up:
            uploaded_file = st.file_uploader(
                "رفع ملف (PDF, Excel, CSV)",
                type=["pdf", "xlsx", "xls", "csv"],
                key=f"fin_up_{symbol}"
            )
        with c_pst:
            pasted_text = st.text_area("أو الصق النص هنا", height=120, key=f"fin_paste_{symbol}")

        cbtn1, cbtn2 = st.columns(2)
        with cbtn1:
            if st.button("⚡ تحديث آلي (Yahoo + بدائل)", key=f"fin_sync_{symbol}"):
                ok, msg = sync_auto_yahoo(symbol)
                (st.success(msg) if ok else st.error(msg))

        with cbtn2:
            if st.button("🚀 معالجة البيانات", key=f"fin_parse_{symbol}"):
                with st.spinner("جاري التحليل..."):
                    results, detected_symbol, err = parser.process_file_or_text(uploaded_file, pasted_text)

                if err:
                    st.error(err)
                    return
                if not results:
                    st.warning("لم نتمكن من استخراج بيانات مفيدة. جرّب لصق جدول بشكل أوضح.")
                    return

                st.success(f"تم استخراج {len(results)} سجلات!")

                target_symbol = detected_symbol or get_ticker_symbol(symbol)
                if detected_symbol and detected_symbol != get_ticker_symbol(symbol):
                    st.warning(f"⚠️ يبدو أن الملف لشركة {detected_symbol}، وأنت في {symbol}.")
                    if st.checkbox("استخدم الرمز المكتشف؟", value=True, key=f"fin_use_detect_{symbol}"):
                        target_symbol = detected_symbol

                preview_df = pd.DataFrame([{"Date": r["date"], **(r["data"] or {})} for r in results])
                _render_df_pretty(preview_df, "معاينة البيانات المستخرجة")

                if st.button("💾 حفظ البيانات", key=f"fin_save_{symbol}"):
                    saved = 0
                    for r in results:
                        if save_financial_record(target_symbol, r["date"], r["data"], "Annual", "File/Paste"):
                            saved += 1
                    st.success(f"تم حفظ {saved} سجل/سجلات")
                    st.rerun()
# ==============================================================
# ✅ Backward-compat exports (DO NOT REMOVE)
# ==============================================================

# بعض الصفحات القديمة تستورد الاسم هذا مباشرة:
# from financial_analysis import get_advanced_fundamental_ratios
# فإذا الملف الحالي عندك ما عاد يعرّفها، يصير ImportError.

try:
    get_advanced_fundamental_ratios  # noqa
except NameError:
    def get_advanced_fundamental_ratios(symbol):
        # fallback: استخدم الدالة المتوفرة عندك
        return get_fundamental_ratios(symbol)