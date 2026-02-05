# financial_analysis/yahoo_data.py
import time
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd
import streamlit as st

from market_data import get_ticker_symbol
from .utils import HEADERS, _safe_date_str

# Web (اختياري)
try:
    import requests  # type: ignore
except ImportError as e:
    requests = None
    from osoli_logging import log_exception
    log_exception(e, "Optional dependency missing: requests", level="WARNING")


def _safe_snippet(text: str | None, n: int = 200) -> str:
    """Return a short one-line snippet for diagnostics without risking SyntaxErrors."""
    try:
        return ((text or "")[:n]).replace("\n", " ").replace("\r", " ")
    except Exception:
        return ""


# ==============================================================
# ✅ Yahoo QuoteSummary JSON (Most stable for statements)
# ==============================================================
_YF_SESSION = None

# Last Yahoo fetch diagnostics (best-effort)
_LAST_YAHOO_STATUS = None  # type: ignore
_LAST_YAHOO_ERROR = None  # type: ignore


def _yf_session():
    global _YF_SESSION
    if _YF_SESSION is None:
        if not requests:
            return {}
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
    """Best-effort GET JSON with basic retry/backoff and diagnostics."""
    global _LAST_YAHOO_STATUS, _LAST_YAHOO_ERROR

    _LAST_YAHOO_STATUS = None
    _LAST_YAHOO_ERROR = None

    if not requests:
        _LAST_YAHOO_ERROR = "requests not available"
        return {}

    ses = _yf_session()
    if not ses:
        _LAST_YAHOO_ERROR = "Yahoo session could not be initialized"
        return {}

    from osoli_logging import log_exception

    last_status = None
    last_err = None

    for i in range(retries + 1):
        try:
            r = ses.get(url, timeout=timeout)
            last_status = r.status_code

            if r.status_code == 200:
                try:
                    data = r.json() or {}
                    _LAST_YAHOO_STATUS = 200
                    return data
                except Exception as e:
                    last_err = f"Invalid JSON response: {e}"
                    _LAST_YAHOO_STATUS = 200
                    _LAST_YAHOO_ERROR = last_err
                    return {}

            # Common blocking / auth statuses
            if r.status_code in (401, 403):
                snippet = _safe_snippet(getattr(r, 'text', None))
                last_err = f"Access blocked by Yahoo (HTTP {r.status_code}). Snippet: {snippet}"
                _LAST_YAHOO_STATUS = r.status_code
                _LAST_YAHOO_ERROR = last_err
                return {}

            # Transient / rate-limit statuses
            if r.status_code in (429, 503):
                snippet = _safe_snippet(getattr(r, 'text', None))
                last_err = f"Transient Yahoo error (HTTP {r.status_code}). Snippet: {snippet}"
                _LAST_YAHOO_STATUS = r.status_code
                _LAST_YAHOO_ERROR = last_err
                time.sleep(sleep * (2 if r.status_code == 429 else 1))
                continue

            snippet = _safe_snippet(getattr(r, 'text', None))
            last_err = f"HTTP {r.status_code}. Snippet: {snippet}"
            _LAST_YAHOO_STATUS = r.status_code
            _LAST_YAHOO_ERROR = last_err
            return {}

        except Exception as e:
            last_err = f"Request error: {e}"
            _LAST_YAHOO_ERROR = last_err
            log_exception(e, "Yahoo QuoteSummary request failed", level="WARNING")

        if i < retries:
            time.sleep(sleep)

    _LAST_YAHOO_STATUS = last_status
    _LAST_YAHOO_ERROR = last_err
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


def diagnose_quote_summary(symbol: str, modules: List[str] | None = None) -> Dict[str, Any]:
    """Return best-effort diagnostics for Yahoo QuoteSummary fetch."""
    sym = get_ticker_symbol(symbol)
    mods = modules or ["incomeStatementHistory", "balanceSheetHistory", "cashflowStatementHistory"]
    url = (
        "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
        f"{sym}?modules=" + ",".join(mods)
    )

    # Perform a tiny fetch to populate diagnostics
    _ = _http_get_json(url)
    status = _LAST_YAHOO_STATUS
    err = _LAST_YAHOO_ERROR

    hint = None
    if status in (401, 403):
        hint = "Yahoo غالبًا حظر الطلب (403/401). جرّب VPN/تغيير IP أو انتظر ثم أعد المحاولة."
    elif status == 429:
        hint = "Rate limit (429). انتظر 1-2 دقيقة ثم أعد المحاولة."
    elif status == 503:
        hint = "خدمة Yahoo مؤقتًا غير متاحة (503). أعد المحاولة لاحقًا."
    elif err == "requests not available":
        hint = "مكتبة requests غير مثبتة. ثبّتها أو تأكد أنها ضمن requirements."
    elif not status and err:
        hint = "فشل اتصال/شبكة. تحقق من الإنترنت أو قيود السيرفر."

    return {"symbol": sym, "url": url, "status": status, "error": err, "hint": hint}


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
# ✅ Full Statements (All line-items) from Yahoo QuoteSummary JSON
# ==============================================================
def _extract_numeric_items(stmt: dict) -> Dict[str, float]:
    """Extract all numeric fields from a Yahoo statement record."""
    out: Dict[str, float] = {}
    if not isinstance(stmt, dict):
        return out

    # keys to skip: metadata / non-numeric
    skip = {
        "maxAge",
        "endDate",
        "asOfDate",
        "periodEndDate",
        "currencyCode",
        "periodType",
        "type",
        "reportedCurrency",
        "exchangeRate",
    }

    for k, v in stmt.items():
        if k in skip:
            continue
        # Yahoo numbers usually: {"raw":..., "fmt":...}
        if isinstance(v, dict) and ("raw" in v or "fmt" in v):
            try:
                out[str(k)] = float(v.get("raw") if v.get("raw") is not None else _yf_raw(v, default=0.0))
            except Exception:
                continue
        elif isinstance(v, (int, float)):
            out[str(k)] = float(v)
        # ignore nested dicts/lists
    return out


def fetch_full_financial_statements_yahoo_json(
    symbol: str,
    period_type: str = "Annual",
    *,
    as_thousands: bool = True,
    include_ttm: bool = True,
) -> Dict[str, Any]:
    """
    Fetch full Income/Balance/Cashflow statements (all available line-items)
    from Yahoo QuoteSummary JSON.

    Returns:
      {
        "Annual": {"income": [{"date":..., "data": {...}},...], "balance":[...], "cashflow":[...]},
        "Quarterly": {...},
        "TTM": {...}  # derived (income/cashflow sum last 4 quarters; balance = latest quarter)
      }

    Notes:
      - Yahoo raw values are typically in *currency units*. If as_thousands=True,
        we divide by 1000 to match Yahoo Finance table display ("all numbers in thousands").
      - TTM is *computed* from Quarterly data.
    """
    sym = get_ticker_symbol(symbol)
    freq = str(period_type or "Annual").strip().title()
    if freq not in ("Annual", "Quarterly", "All"):
        freq = "Annual"

    # Always fetch both annual + quarterly once for stability
    modules = [
        "incomeStatementHistory",
        "incomeStatementHistoryQuarterly",
        "balanceSheetHistory",
        "balanceSheetHistoryQuarterly",
        "cashflowStatementHistory",
        "cashflowStatementHistoryQuarterly",
    ]
    root = _yahoo_quote_summary(sym, modules)
    if not root:
        return {}

    def get_list(key: str) -> List[dict]:
        return _extract_stmt_list(root, key)

    annual = {
        "income": get_list("incomeStatementHistory"),
        "balance": get_list("balanceSheetHistory"),
        "cashflow": get_list("cashflowStatementHistory"),
    }
    quarterly = {
        "income": get_list("incomeStatementHistoryQuarterly"),
        "balance": get_list("balanceSheetHistoryQuarterly"),
        "cashflow": get_list("cashflowStatementHistoryQuarterly"),
    }

    def normalize(lst: List[dict]) -> List[Dict[str, Any]]:
        out = []
        for rec in lst or []:
            if not isinstance(rec, dict):
                continue
            d = _yf_date_str(rec.get("endDate") or rec.get("asOfDate") or rec.get("periodEndDate"))
            data = _extract_numeric_items(rec)
            if not data:
                continue
            if as_thousands:
                data = {k: (float(v) / 1000.0) for k, v in data.items()}
            out.append({"date": d, "data": data})
        out = sorted(out, key=lambda x: x.get("date", ""), reverse=True)
        return out

    out = {
        "Annual": {k: normalize(v) for k, v in annual.items()},
        "Quarterly": {k: normalize(v) for k, v in quarterly.items()},
    }

    if include_ttm:
        # derive from quarterly (if available)
        q_income = out["Quarterly"].get("income") or []
        q_cash = out["Quarterly"].get("cashflow") or []
        q_balance = out["Quarterly"].get("balance") or []

        def ttm_sum(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not records or len(records) < 1:
                return {}
            # use last 4 quarters if possible, else whatever available
            recent = records[:4]
            # union of keys
            keys = set()
            for r in recent:
                keys |= set((r.get("data") or {}).keys())
            sums = {}
            for k in keys:
                s = 0.0
                for r in recent:
                    s += float((r.get("data") or {}).get(k, 0.0) or 0.0)
                sums[k] = s
            return {"date": recent[0].get("date"), "data": sums}

        def latest_snapshot(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not records:
                return {}
            return {"date": records[0].get("date"), "data": (records[0].get("data") or {})}

        ttm_income = ttm_sum(q_income)
        ttm_cash = ttm_sum(q_cash)
        ttm_balance = latest_snapshot(q_balance)

        ttm = {"income": [], "balance": [], "cashflow": []}
        if ttm_income:
            ttm["income"] = [ttm_income]
        if ttm_balance:
            ttm["balance"] = [ttm_balance]
        if ttm_cash:
            ttm["cashflow"] = [ttm_cash]
        out["TTM"] = ttm

    if freq == "Annual":
        return {"Annual": out["Annual"], "TTM": out.get("TTM", {})}
    if freq == "Quarterly":
        return {"Quarterly": out["Quarterly"], "TTM": out.get("TTM", {})}
    return out
