# financial_analysis/yahoo_data.py
import time
from datetime import datetime
import re
from typing import Dict, List, Any

import pandas as pd
import streamlit as st

from market_data import get_ticker_symbol
from .utils import HEADERS, _safe_date_str

# Web (اختياري)
try:
    import requests
except Exception:
    requests = None

# ==============================
# Diagnostics (آخر تشخيص لطلبات Yahoo)
# ==============================
_LAST_YAHOO_DIAGNOSTICS = {
    "ts": None,
    "url": None,
    "status": None,
    "error": None,
    "snippet": None,
    "hint": None,
}


def _set_last_diag(url=None, status=None, error=None, snippet=None, hint=None):
    try:
        _LAST_YAHOO_DIAGNOSTICS.update(
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "url": url,
                "status": status,
                "error": str(error) if error else None,
                "snippet": snippet,
                "hint": hint,
            }
        )
    except Exception:
        pass


def get_last_yahoo_diagnostics() -> Dict[str, Any]:
    """Return last Yahoo request diagnostics (safe for UI)."""
    return dict(_LAST_YAHOO_DIAGNOSTICS)


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

        if sum(abs(float(v or 0.0)) for v in data.values()) == 0:
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
    from .store import get_stored_financials_df, save_financial_record
    from .parsers import fetch_financials_from_argaam, fetch_financials_from_google_finance

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
# 🩺 Diagnostics helpers (QuoteSummary)
# ==============================================================
def diagnose_quote_summary(symbol: str) -> Dict[str, Any]:
    """Run a lightweight probe against quoteSummary and return status + hint."""
    symbol = get_ticker_symbol(symbol)
    try:
        data = _yahoo_quote_summary(symbol, modules=["price"])
        diag = get_last_yahoo_diagnostics()
        if not data:
            diag["hint"] = diag.get("hint") or "Empty response"
        return diag
    except Exception as e:
        diag = get_last_yahoo_diagnostics()
        diag["error"] = str(e)
        # Provide a helpful hint for the most common cases
        status = diag.get("status")
        if status == 429:
            diag["hint"] = "Rate limit (429) — حاول بعد 1-2 دقيقة أو فعّل التخزين المحلي"
        elif status in (401, 403):
            diag["hint"] = "Blocked/Forbidden — جرّب لاحقًا أو استخدم مصدر بديل"
        elif status == 404:
            diag["hint"] = "Symbol not found / endpoint changed"
        return diag


# ==============================================================
# 📚 Full Statements (QuoteSummary raw JSON + optional HTML fallback)
# ==============================================================
def fetch_full_financial_statements_yahoo_json(symbol: str, period: str = "annual") -> Dict[str, Any]:
    """Fetch *raw* full statements dict from Yahoo quoteSummary.
    Returns a dict with keys: income, balance, cash, meta.
    Non-breaking: returns empty dict on failure.
    """
    symbol = get_ticker_symbol(symbol)
    period = (period or "annual").lower()
    try:
        modules = ["incomeStatementHistory", "incomeStatementHistoryQuarterly",
                   "balanceSheetHistory", "balanceSheetHistoryQuarterly",
                   "cashflowStatementHistory", "cashflowStatementHistoryQuarterly"]
        raw = _yahoo_quote_summary(symbol, modules=modules) or {}
        # quoteSummary structure: {"quoteSummary":{"result":[{...}],"error":...}}
        result = (raw.get("quoteSummary", {}) or {}).get("result") or []
        if not result:
            return {}
        payload = result[0] or {}
        out = {"meta": {"symbol": symbol, "period": period}}
        if period.startswith("q"):
            out["income"] = payload.get("incomeStatementHistoryQuarterly") or {}
            out["balance"] = payload.get("balanceSheetHistoryQuarterly") or {}
            out["cash"] = payload.get("cashflowStatementHistoryQuarterly") or {}
        else:
            out["income"] = payload.get("incomeStatementHistory") or {}
            out["balance"] = payload.get("balanceSheetHistory") or {}
            out["cash"] = payload.get("cashflowStatementHistory") or {}
        return out
    except Exception:
        # diagnostics are already recorded by _http_get_json
        return {}


def _parse_yahoo_root_app_main(html: str) -> Dict[str, Any]:
    """Extract Root.App.main JSON from Yahoo HTML (best-effort)."""
    # Yahoo embeds JSON in: root.App.main = {...};
    m = re.search(r"root\.App\.main\s*=\s*(\{.*?\});\s*\n", html, flags=re.DOTALL)
    if not m:
        m = re.search(r"root\.App\.main\s*=\s*(\{.*?\});", html, flags=re.DOTALL)
    if not m:
        return {}
    blob = m.group(1)
    try:
        import json as _json
        return _json.loads(blob)
    except Exception:
        return {}


def fetch_full_financial_statements_yahoo_html(symbol: str) -> Dict[str, Any]:
    """HTML fallback: fetch Yahoo quote page and try to extract quoteSummary-like stores.
    Returns empty dict on failure.
    """
    symbol = get_ticker_symbol(symbol)
    if not requests:
        return {}
    url = f"https://finance.yahoo.com/quote/{symbol}/financials?p={symbol}"
    try:
        s = _yf_session()
        if not s:
            return {}
        r = s.get(url, timeout=12)
        snippet = (r.text or "")[:200].replace("\n", " ")
        _set_last_diag(url=url, status=r.status_code, error=None, snippet=snippet, hint=None)
        if r.status_code != 200:
            if r.status_code == 429:
                _set_last_diag(url=url, status=429, error="HTTP 429", snippet=snippet, hint="Rate limit (429)")
            return {}
        root = _parse_yahoo_root_app_main(r.text or "")
        # Try to reach a store that contains quoteSummary-like data
        stores = (((root.get("context") or {}).get("dispatcher") or {}).get("stores") or {})
        qs = stores.get("QuoteSummaryStore") or {}
        if qs:
            return {"meta": {"symbol": symbol, "period": "html"}, "quoteSummaryStore": qs}
        return {"meta": {"symbol": symbol, "period": "html"}, "root": root}
    except Exception as e:
        _set_last_diag(url=url, status=None, error=e, snippet=None, hint="HTML fallback error")
        return {}
