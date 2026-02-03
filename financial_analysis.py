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
    ✅ إصلاحات مهمة تمنع فشل الإدخال وسقوط صفحة المستشار:
    - financialstatements lowercase بدون quotes
    - قص source/period_type إلى 20 (لأن DB عندك VARCHAR(20))
    """
    try:
        symbol = get_ticker_symbol(symbol)
        date_str = _safe_date_str(date_str)

        # ✅ DB columns are VARCHAR(20)
        period_type = str(period_type or "Annual").strip().title()[:20]
        source = str(source or "Manual").strip()[:20]

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
        period_type = str(period_type or "Annual").strip().title()[:20]

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
        if not requests:
            return {}
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
    if not requests:
        return {}

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
    ptype = ptype[:20]

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


def _compute_dupont(curr_row: pd.Series) -> dict:
    out = {
        "DuPont_Profit_Margin": 0.0,
        "DuPont_Asset_Turnover": 0.0,
        "DuPont_Equity_Multiplier": 0.0,
        "ROE": 0.0,
        "ROA": 0.0,
        "Asset_Turnover": 0.0,
    }
    try:
        rev = _safe_float(curr_row.get("revenue", 0))
        ni = _safe_float(curr_row.get("net_income", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))
        eq = _safe_float(curr_row.get("total_equity", 0))

        pm = _safe_div(ni, rev, 0.0)
        at = _safe_div(rev, assets, 0.0)
        em = _safe_div(assets, eq, 0.0)

        roe = pm * at * em if (pm and at and em) else _safe_div(ni, eq, 0.0)
        roa = _safe_div(ni, assets, 0.0)

        out["DuPont_Profit_Margin"] = float(pm)
        out["DuPont_Asset_Turnover"] = float(at)
        out["DuPont_Equity_Multiplier"] = float(em)
        out["ROE"] = float(roe)
        out["ROA"] = float(roa)
        out["Asset_Turnover"] = float(at)
    except Exception:
        pass
    return out


def _compute_liquidity_leverage(curr_row: pd.Series, prev_row: pd.Series = None) -> dict:
    out = {
        "Current_Ratio": 0.0,
        "Working_Capital": 0.0,
        "Debt_to_Equity": 0.0,
        "Liabilities_to_Assets": 0.0,
        "LT_Debt_Trend": 0.0,
    }
    try:
        ca = _safe_float(curr_row.get("current_assets", 0))
        cl = _safe_float(curr_row.get("current_liabilities", 0))
        ltd = _safe_float(curr_row.get("long_term_debt", 0))
        liab = _safe_float(curr_row.get("total_liabilities", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))
        eq = _safe_float(curr_row.get("total_equity", 0))

        wc = ca - cl
        cr = _safe_div(ca, cl, 0.0)
        dte = _safe_div(ltd, eq, 0.0) if eq > 0 else _safe_div(liab, assets, 0.0)
        lta = _safe_div(liab, assets, 0.0)

        out["Working_Capital"] = float(wc)
        out["Current_Ratio"] = float(cr)
        out["Debt_to_Equity"] = float(dte)
        out["Liabilities_to_Assets"] = float(lta)

        if prev_row is not None:
            ltd_p = _safe_float(prev_row.get("long_term_debt", 0))
            if ltd_p != 0:
                out["LT_Debt_Trend"] = float((ltd - ltd_p) / abs(ltd_p))
    except Exception:
        pass
    return out


def _compute_earnings_quality(curr_row: pd.Series) -> dict:
    out = {
        "OCF_to_NetIncome": 0.0,
        "Accruals_to_Assets": 0.0,
        "OCF_Margin": 0.0,
    }
    try:
        ni = _safe_float(curr_row.get("net_income", 0))
        ocf = _safe_float(curr_row.get("operating_cash_flow", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))
        rev = _safe_float(curr_row.get("revenue", 0))

        out["OCF_to_NetIncome"] = float(_safe_div(ocf, ni, 0.0)) if ni != 0 else (1.0 if ocf > 0 else 0.0)
        out["Accruals_to_Assets"] = float(_safe_div((ni - ocf), assets, 0.0))
        out["OCF_Margin"] = float(_safe_div(ocf, rev, 0.0))
    except Exception:
        pass
    return out


def _compute_altman_z_best_effort(symbol: str, curr_row: pd.Series, yahoo_info: dict) -> dict:
    out = {
        "Altman_Z": 0.0,
        "Altman_Z_Quality": "partial",
    }
    try:
        ta = _safe_float(curr_row.get("total_assets", 0))
        if ta <= 0:
            return out

        ca = _safe_float(curr_row.get("current_assets", 0))
        cl = _safe_float(curr_row.get("current_liabilities", 0))
        wc = ca - cl

        tl = _safe_float(curr_row.get("total_liabilities", 0))
        sales = _safe_float(curr_row.get("revenue", 0))

        ebit = 0.0
        retained = 0.0

        ebitda = _safe_float(yahoo_info.get("ebitda"))
        if ebitda > 0:
            ebit = 0.7 * ebitda

        mve = _safe_float(yahoo_info.get("marketCap"))

        z = 0.0
        z += 1.2 * _safe_div(wc, ta, 0.0)
        z += 1.4 * _safe_div(retained, ta, 0.0)
        z += 3.3 * _safe_div(ebit, ta, 0.0)
        z += 0.6 * _safe_div(mve, tl, 0.0) if tl > 0 else 0.0
        z += 1.0 * _safe_div(sales, ta, 0.0)

        out["Altman_Z"] = float(z)
        out["Altman_Z_Quality"] = "full" if (ebit > 0 and mve > 0 and sales > 0 and tl > 0) else "partial"
    except Exception:
        pass
    return out


def _compute_sgr(roe: float, yahoo_info: dict) -> dict:
    out = {"SGR": 0.0, "Payout_Ratio": 0.0, "Retention_Ratio": 0.0, "SGR_Estimated": 0}
    try:
        payout = _safe_float(yahoo_info.get("payoutRatio"))
        if payout <= 0 or payout >= 1:
            payout = 0.30
            out["SGR_Estimated"] = 1

        retention = max(0.0, min(1.0, 1.0 - payout))
        out["Payout_Ratio"] = float(payout)
        out["Retention_Ratio"] = float(retention)
        out["SGR"] = float(_safe_float(roe) * retention)
    except Exception:
        pass
    return out


def _compute_valuation_pack(yahoo_info: dict) -> dict:
    out = {
        "PE_Trailing": 0.0,
        "PE_Forward": 0.0,
        "PEG": 0.0,
        "PB": 0.0,
        "MarketCap": 0.0,
        "EV": 0.0,
        "EV_to_EBITDA": 0.0,
        "Dividend_Yield": 0.0,
    }
    try:
        out["PE_Trailing"] = float(_safe_float(yahoo_info.get("trailingPE")))
        out["PE_Forward"] = float(_safe_float(yahoo_info.get("forwardPE")))
        out["PEG"] = float(_safe_float(yahoo_info.get("pegRatio")))
        out["PB"] = float(_safe_float(yahoo_info.get("priceToBook")))
        out["MarketCap"] = float(_safe_float(yahoo_info.get("marketCap")))
        out["EV"] = float(_safe_float(yahoo_info.get("enterpriseValue")))
        out["EV_to_EBITDA"] = float(_safe_float(yahoo_info.get("enterpriseToEbitda")))
        out["Dividend_Yield"] = float(_safe_float(yahoo_info.get("dividendYield")))
    except Exception:
        pass
    return out


def _score_fundamentals(metrics: dict) -> Tuple[int, str, List[str]]:
    score = 0
    opinions: List[str] = []

    try:
        piot = int(metrics.get("Piotroski_Score", 0) or 0)
        roe = _safe_float(metrics.get("ROE", 0))
        roa = _safe_float(metrics.get("ROA", 0))
        cr = _safe_float(metrics.get("Current_Ratio", 0))
        lta = _safe_float(metrics.get("Liabilities_to_Assets", 0))
        ocf_ni = _safe_float(metrics.get("OCF_to_NetIncome", 0))
        altz = _safe_float(metrics.get("Altman_Z", 0))
        altq = str(metrics.get("Altman_Z_Quality", "partial"))

        pe = _safe_float(metrics.get("PE_Trailing", 0))
        peg = _safe_float(metrics.get("PEG", 0))

        if piot >= 7:
            score += 3
            opinions.append("💎 Piotroski مرتفع (جودة مالية قوية)")
        elif piot <= 3:
            score -= 2
            opinions.append("⚠️ Piotroski منخفض (مخاطر مالية)")

        if roe >= 0.12:
            score += 2
            opinions.append("✅ ROE قوي (>= 12%)")
        elif roe <= 0.03 and roe > 0:
            score -= 1
            opinions.append("⚠️ ROE ضعيف")

        if roa >= 0.05:
            score += 1

        if cr >= 1.2:
            score += 1
            opinions.append("✅ السيولة جيدة (Current Ratio مناسب)")
        elif cr > 0 and cr < 0.9:
            score -= 1
            opinions.append("⚠️ السيولة ضعيفة (Current Ratio منخفض)")

        if lta > 0.75:
            score -= 1
            opinions.append("⚠️ التزامات مرتفعة مقارنة بالأصول")
        elif 0 < lta <= 0.55:
            score += 1

        if ocf_ni >= 1.0:
            score += 1
            opinions.append("✅ جودة أرباح جيدة (OCF ≥ Net Income)")
        elif 0 < ocf_ni < 0.6:
            score -= 1
            opinions.append("⚠️ جودة أرباح أقل (OCF أقل من صافي الربح)")

        if altz > 0:
            if altz >= 3.0:
                score += 2
                opinions.append("✅ Altman Z قوي (مخاطر إفلاس منخفضة)")
            elif altz < 1.8:
                score -= 2
                opinions.append("⛔ Altman Z منخفض (مخاطر أعلى)")
            if altq != "full":
                opinions.append("ℹ️ Altman Z محسوب بشكل جزئي حسب المتوفر")

        if peg > 0 and peg <= 1.2:
            score += 1
            opinions.append("✅ PEG جيد (تقييم معقول مقابل النمو)")
        elif peg > 2.5:
            score -= 1
            opinions.append("⚠️ PEG مرتفع (تقييم مكلف)")

        if pe > 0 and pe <= 14:
            score += 1
        elif pe >= 35:
            score -= 1

    except Exception:
        pass

    score = int(max(0, min(10, score)))

    if score >= 8:
        rating = "قوي"
    elif score >= 6:
        rating = "جيد"
    elif score >= 4:
        rating = "متوسط"
    else:
        rating = "ضعيف"

    return score, rating, opinions


def get_advanced_fundamental_ratios(symbol):
    metrics = {
        "Fair_Value_Graham": 0.0,
        "Piotroski_Score": 0,
        "Financial_Health": "غير متوفر",
        "Score": 0,
        "Rating": "N/A",
        "Opinions": "",
        "ROE": 0.0,
        "ROA": 0.0,
        "DuPont_Profit_Margin": 0.0,
        "DuPont_Asset_Turnover": 0.0,
        "DuPont_Equity_Multiplier": 0.0,
        "Current_Ratio": 0.0,
        "Working_Capital": 0.0,
        "Debt_to_Equity": 0.0,
        "Liabilities_to_Assets": 0.0,
        "LT_Debt_Trend": 0.0,
        "OCF_to_NetIncome": 0.0,
        "Accruals_to_Assets": 0.0,
        "OCF_Margin": 0.0,
        "Altman_Z": 0.0,
        "Altman_Z_Quality": "partial",
        "SGR": 0.0,
        "Payout_Ratio": 0.0,
        "Retention_Ratio": 0.0,
        "SGR_Estimated": 0,
        "PE_Trailing": 0.0,
        "PE_Forward": 0.0,
        "PEG": 0.0,
        "PB": 0.0,
        "MarketCap": 0.0,
        "EV": 0.0,
        "EV_to_EBITDA": 0.0,
        "Dividend_Yield": 0.0,
    }

    symbol = get_ticker_symbol(symbol)

    df = get_stored_financials_df(symbol, "Annual")
    if df.empty:
        df = get_stored_financials_df(symbol, "Quarterly")
    if df.empty:
        return metrics

    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr

    info = _fetch_yahoo_info(symbol)

    try:
        score = 0

        net_income_c = _safe_float(curr.get("net_income", 0))
        ocf_c = _safe_float(curr.get("operating_cash_flow", 0))
        assets_c = _safe_float(curr.get("total_assets", 1)) or 1.0

        net_income_p = _safe_float(prev.get("net_income", 0))
        assets_p = _safe_float(prev.get("total_assets", 1)) or 1.0

        if net_income_c > 0:
            score += 1
        if ocf_c > 0:
            score += 1

        roa_c = net_income_c / assets_c
        roa_p = net_income_p / assets_p
        if roa_c > roa_p:
            score += 1

        if ocf_c > net_income_c:
            score += 1

        ltd_c = _safe_float(curr.get("long_term_debt", 0))
        ltd_p = _safe_float(prev.get("long_term_debt", 0))
        if ltd_c < ltd_p:
            score += 1

        ca_c = _safe_float(curr.get("current_assets", 0))
        cl_c = _safe_float(curr.get("current_liabilities", 0))
        ca_p = _safe_float(prev.get("current_assets", 0))
        cl_p = _safe_float(prev.get("current_liabilities", 0))

        cr_c = ca_c / (cl_c or 1.0)
        cr_p = ca_p / (cl_p or 1.0)
        if cr_c > cr_p:
            score += 1

        eq_c = _safe_float(curr.get("total_equity", 0))
        eq_p = _safe_float(prev.get("total_equity", 0))
        if eq_c > eq_p and eq_c > 0:
            score += 1

        piotroski = int(min(max(score + 2, 0), 9))
        metrics["Piotroski_Score"] = piotroski
        metrics["Score"] = piotroski

        dup = _compute_dupont(curr)
        liq = _compute_liquidity_leverage(curr, prev)
        eqy = _compute_earnings_quality(curr)

        metrics.update(dup)
        metrics.update(liq)
        metrics.update(eqy)

        metrics.update(_compute_valuation_pack(info))

        try:
            eps = _safe_float(info.get("trailingEps"))
            bvps = _safe_float(info.get("bookValue"))
            if eps > 0 and bvps > 0:
                metrics["Fair_Value_Graham"] = float((22.5 * eps * bvps) ** 0.5)
        except Exception:
            pass

        metrics.update(_compute_altman_z_best_effort(symbol, curr, info))
        metrics.update(_compute_sgr(metrics.get("ROE", 0.0), info))

        fscore10, rating, adv_ops = _score_fundamentals(metrics)

        if metrics["Piotroski_Score"] >= 7:
            metrics["Financial_Health"] = "جيد"
        elif metrics["Piotroski_Score"] <= 3:
            metrics["Financial_Health"] = "هش"
        else:
            metrics["Financial_Health"] = "متوسط"

        if ocf_c < 0:
            adv_ops.append("⚠️ التدفق النقدي التشغيلي سالب")

        if int(metrics.get("SGR_Estimated", 0)) == 1:
            adv_ops.append("ℹ️ SGR محسوب بافتراض payoutRatio (تقديري)")

        if _safe_float(metrics.get("PE_Trailing", 0)) == 0 and _safe_float(metrics.get("PEG", 0)) == 0:
            adv_ops.append("ℹ️ بيانات التقييم (PE/PEG) غير متوفرة من Yahoo")

        metrics["Rating"] = rating
        metrics["Score"] = int(max(fscore10, int(metrics.get("Piotroski_Score", 0) or 0)))
        metrics["Opinions"] = " | ".join([str(x) for x in adv_ops if str(x).strip()])[:1200]

    except Exception:
        pass

    return metrics


def get_fundamental_ratios(symbol):
    return get_advanced_fundamental_ratios(symbol)


# ==============================================================
# 📝 6) Thesis (DB fixed)
# ==============================================================
def get_thesis(symbol):
    symbol = get_ticker_symbol(symbol)
    try:
        df = fetch_table("investmentthesis")
        if df is None or df.empty:
            return None
        sub = df[df["symbol"].astype(str) == symbol]
        if sub.empty:
            return None
        return sub.iloc[0]
    except Exception:
        return None


def save_thesis(symbol, thesis_text, target_price, recommendation):
    symbol = get_ticker_symbol(symbol)
    thesis_text = str(thesis_text or "")
    recommendation = str(recommendation or "Hold")[:20]
    try:
        tp = _safe_float(target_price)
    except Exception:
        tp = 0.0

    today = datetime.now().strftime("%Y-%m-%d")

    execute_query(
        """
        INSERT INTO investmentthesis (symbol, thesis_text, target_price, recommendation, last_updated)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (symbol)
        DO UPDATE SET
            thesis_text=EXCLUDED.thesis_text,
            target_price=EXCLUDED.target_price,
            recommendation=EXCLUDED.recommendation,
            last_updated=EXCLUDED.last_updated;
        """,
        (symbol, thesis_text, tp, recommendation, today),
    )


# ==============================================================
# 🖥️ (Optional) Standalone UI (not required by views.py)
# ==============================================================
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
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("F-Score", f"{metrics['Piotroski_Score']}/9", metrics["Financial_Health"])
            c2.metric(
                "Graham Value",
                f"{metrics.get('Fair_Value_Graham', 0):,.2f}" if metrics.get("Fair_Value_Graham") else "N/A",
            )
            c3.write(metrics.get("Opinions", ""))

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
                st.dataframe(df, use_container_width=True)

            with st.expander("📌 مؤشرات متقدمة (DuPont / Altman / Valuation / SGR)"):
                try:
                    adv = {
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
                    }
                    st.json(adv)
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
                key=f"fin_up_{symbol}",
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
                st.dataframe(preview_df, use_container_width=True)

                if st.button("💾 حفظ البيانات", key=f"fin_save_{symbol}"):
                    saved = 0
                    for r in results:
                        if save_financial_record(target_symbol, r["date"], r["data"], "Annual", "File/Paste"):
                            saved += 1
                    st.success(f"تم حفظ {saved} سجل/سجلات")
                    st.rerun()