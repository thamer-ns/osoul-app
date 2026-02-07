# financial_analysis/yahoo_data.py
import time
import json
import re
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd
import streamlit as st

from market_data import get_ticker_symbol
from .utils import HEADERS, _safe_date_str

# Web (اختياري)
try:
    import requests  # type: ignore
except Exception:
    requests = None
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
# Last Yahoo fetch metadata (best-effort)
_LAST_YAHOO_TS = None  # type: ignore
_LAST_YAHOO_URL = None  # type: ignore
_LAST_YAHOO_HEADERS = None  # type: ignore



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
    """Best-effort GET JSON with retry/backoff + diagnostics.

    Yahoo QuoteSummary is an unofficial endpoint; it may rate-limit (429) or return HTML.
    This helper keeps the behavior conservative to avoid breaking the app.
    """
    global _LAST_YAHOO_STATUS, _LAST_YAHOO_ERROR, _LAST_YAHOO_TS, _LAST_YAHOO_URL, _LAST_YAHOO_HEADERS

    _LAST_YAHOO_STATUS = None
    _LAST_YAHOO_ERROR = None
    _LAST_YAHOO_URL = url
    _LAST_YAHOO_HEADERS = None
    _LAST_YAHOO_TS = datetime.now().isoformat(timespec="seconds")

    if not requests:
        _LAST_YAHOO_ERROR = "requests not available"
        return {}

    ses = _yf_session()
    if not ses:
        _LAST_YAHOO_ERROR = "session not initialized"
        return {}

    last_status = None
    last_err = None

    for i in range(retries + 1):
        try:
            r = ses.get(url, timeout=timeout)
            last_status = getattr(r, "status_code", None)
            _LAST_YAHOO_STATUS = last_status
            try:
                _LAST_YAHOO_HEADERS = dict(getattr(r, "headers", {}) or {})
            except Exception:
                _LAST_YAHOO_HEADERS = None

            if last_status == 200:
                try:
                    return r.json() or {}
                except Exception:
                    # Sometimes returns HTML/empty: keep safe
                    last_err = f"Non-JSON response: {_safe_snippet(getattr(r, 'text', None))}"
            elif last_status in (429, 503):
                last_err = f"Transient Yahoo error (HTTP {last_status})"
                # backoff a bit (429 usually needs longer)
                time.sleep(sleep * (2 if last_status == 429 else 1))
            else:
                # 401/403/404/etc
                last_err = f"Yahoo HTTP {last_status}: {_safe_snippet(getattr(r, 'text', None))}"
        except Exception as e:
            last_err = f"Exception: {type(e).__name__}: {e}"

        if i < retries:
            time.sleep(sleep)

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


def get_last_yahoo_diagnostics() -> Dict[str, Any]:
    """Return last Yahoo fetch diagnostics (status/error/url/time)."""
    return {
        "status": _LAST_YAHOO_STATUS,
        "error": _LAST_YAHOO_ERROR,
        "url": _LAST_YAHOO_URL,
        "ts": _LAST_YAHOO_TS,
        "headers": _LAST_YAHOO_HEADERS,
    }


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



# ==============================================================
# Yahoo HTML (finance.yahoo.com) fallback
# - This is a single-page fetch per statement type and often works
#   even when the quoteSummary endpoint is rate-limited.
# ==============================================================

def _parse_yahoo_root_app_main(html: str) -> dict:
    """Extract root.App.main JSON from Yahoo Finance HTML."""
    if not html:
        return {}
    # Common pattern: root.App.main = {...};
    m = re.search(r"root\.App\.main\s*=\s*(\{.*?\})\s*;\s*\n", html, flags=re.DOTALL)
    if not m:
        # fallback: script tag without newline
        m = re.search(r"root\.App\.main\s*=\s*(\{.*?\})\s*;\s*</script>", html, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}

def _fetch_yahoo_quote_store_from_html(symbol: str, statement: str = "financials") -> dict:
    """Fetch Yahoo Finance statement page and extract QuoteSummaryStore."""
    sym = get_ticker_symbol(symbol).replace("^", "%5E")
    # statement pages: financials, balance-sheet, cash-flow
    page = statement or "financials"
    url = f"https://finance.yahoo.com/quote/{sym}/{page}"
    try:
        r = _session.get(url, timeout=10)
        if r.status_code != 200 or not r.text:
            return {}
        app = _parse_yahoo_root_app_main(r.text)
        store = (
            app.get("context", {})
               .get("dispatcher", {})
               .get("stores", {})
               .get("QuoteSummaryStore", {})
        )
        return store if isinstance(store, dict) else {}
    except Exception:
        return {}

def fetch_full_financial_statements_yahoo_html(symbol: str) -> Dict[str, Any]:
    """Fetch annual+quarterly full statements via Yahoo HTML pages."""
    store_fin = _fetch_yahoo_quote_store_from_html(symbol, "financials")
    store_bal = _fetch_yahoo_quote_store_from_html(symbol, "balance-sheet")
    store_cf = _fetch_yahoo_quote_store_from_html(symbol, "cash-flow")

    def _grab(st: dict, key: str):
        v = st.get(key) if isinstance(st, dict) else None
        return v if isinstance(v, dict) else {}

    annual = {
        "income": _grab(store_fin, "incomeStatementHistory"),
        "balance": _grab(store_bal, "balanceSheetHistory"),
        "cashflow": _grab(store_cf, "cashflowStatementHistory"),
    }
    quarterly = {
        "income": _grab(store_fin, "incomeStatementHistoryQuarterly"),
        "balance": _grab(store_bal, "balanceSheetHistoryQuarterly"),
        "cashflow": _grab(store_cf, "cashflowStatementHistoryQuarterly"),
    }
    ttm = {
        "income": _grab(store_fin, "incomeStatementHistoryTTM"),
        "balance": {},
        "cashflow": _grab(store_cf, "cashflowStatementHistoryTTM"),
    }

    # Normalize using the same logic as JSON path (copy minimal here)
    def _extract_records(module_dict: dict) -> List[Dict[str, Any]]:
        # module_dict example: {'incomeStatementHistory':[...]} or {'incomeStatementHistory':[{'endDate':...}]}
        if not isinstance(module_dict, dict):
            return []
        # find first list in dict
        items = None
        for k, v in module_dict.items():
            if isinstance(v, list):
                items = v
                break
        if not items:
            return []
        out = []
        for item in items:
            if isinstance(item, dict):
                out.append(item)
        return out

    def _normalize_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for r in records:
            end = r.get("endDate") or {}
            date_str = end.get("fmt") if isinstance(end, dict) else None
            if not date_str:
                # sometimes only raw
                raw = end.get("raw") if isinstance(end, dict) else None
                if raw:
                    try:
                        date_str = datetime.utcfromtimestamp(int(raw)).strftime("%Y-%m-%d")
                    except Exception:
                        date_str = None
            # flatten values: {'totalRevenue': {'raw':..., 'fmt':...}}
            flat = {}
            for k, v in r.items():
                if k in ("maxAge", "endDate"):
                    continue
                if isinstance(v, dict):
                    if "raw" in v:
                        flat[k] = v.get("raw")
                    elif "fmt" in v:
                        flat[k] = v.get("fmt")
                else:
                    flat[k] = v
            if date_str:
                out.append({"date": date_str, "data": flat})
        return out

    def _pack(periods: dict) -> dict:
        return {
            "income": _normalize_records(_extract_records(periods.get("income", {}))),
            "balance": _normalize_records(_extract_records(periods.get("balance", {}))),
            "cashflow": _normalize_records(_extract_records(periods.get("cashflow", {}))),
        }

    return {"annual": _pack(annual), "quarterly": _pack(quarterly), "ttm": _pack(ttm)}


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

    # ✅ Manual-only mode by default:
    # إذا refresh=False لا نقوم بأي طلبات شبكة (Yahoo/بدائل) حتى لا يحدث 429 بسبب Rerun في Streamlit.
    # يتم الجلب/المزامنة فقط عبر أزرار "مزامنة" من الواجهة (refresh=True أو sync_*).
    if not refresh:
        if stored is None:
            return pd.DataFrame()
        return stored

    # refresh=True: يسمح بمحاولة الجلب من المصادر الخارجية ثم الحفظ
    records = fetch_financial_statements_yahoo_json(sym, ptype)
    origin = "YahooJSON" if records else None

    if not records and ptype == "Annual":
        try:
            d = fetch_financials_from_argaam(sym) or {}
            if d:
                records = [{"date": d.get("date") or datetime.now().strftime("%Y-12-31"), "data": d}]
                origin = "Argaam"
        except Exception:
            pass

    if not records and ptype == "Annual":
        try:
            d2 = fetch_financials_from_google_finance(sym) or {}
            if d2:
                records = [{"date": d2.get("date") or datetime.now().strftime("%Y-12-31"), "data": d2}]
                origin = "GoogleFinance"
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
                source=str(origin or "External"),
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

    Fallback:
      If QuoteSummary is rate-limited / fails, we attempt to fetch from Yahoo HTML pages
      (finance.yahoo.com/quote/<sym>/{financials|balance-sheet|cash-flow}) and parse
      root.App.main -> QuoteSummaryStore.

    Returns:
      {
        "Annual": {"income": [{"date":..., "data": {...}},...], "balance":[...], "cashflow":[...]},
        "Quarterly": {...},
        "TTM": {...}  # derived (income/cashflow sum last 4 quarters; balance = latest quarter)
      }
    """

    sym = get_ticker_symbol(symbol)
    if not sym:
        return {}

    # --- try QuoteSummary JSON first ---
    root = None
    try:
        modules = [
            "incomeStatementHistory",
            "incomeStatementHistoryQuarterly",
            "balanceSheetHistory",
            "balanceSheetHistoryQuarterly",
            "cashflowStatementHistory",
            "cashflowStatementHistoryQuarterly",
            "defaultKeyStatistics",
            "price",
        ]
        root = _yahoo_quote_summary(sym, modules)
    except Exception:
        root = None

    # --- fallback to HTML ---
    if not root:
        try:
            html_pack = fetch_full_financial_statements_yahoo_html(sym)
            if isinstance(html_pack, dict) and (html_pack.get("annual") or html_pack.get("quarterly")):
                out = {
                    "Annual": html_pack.get("annual", {}),
                    "Quarterly": html_pack.get("quarterly", {}),
                }
                if include_ttm and html_pack.get("ttm"):
                    out["TTM"] = html_pack.get("ttm", {})
                return out
        except Exception:
            pass
        return {}

    # ---- original normalization path ----
    res = root.get("quoteSummary", {}).get("result") or []
    if not res:
        return {}
    r0 = res[0] if isinstance(res[0], dict) else {}
    if not r0:
        return {}

    annual = {
        "income": r0.get("incomeStatementHistory") or {},
        "balance": r0.get("balanceSheetHistory") or {},
        "cashflow": r0.get("cashflowStatementHistory") or {},
    }
    quarterly = {
        "income": r0.get("incomeStatementHistoryQuarterly") or {},
        "balance": r0.get("balanceSheetHistoryQuarterly") or {},
        "cashflow": r0.get("cashflowStatementHistoryQuarterly") or {},
    }

    # Build normalized lists
    def _to_list(module_dict: dict) -> list:
        if not isinstance(module_dict, dict):
            return []
        for v in module_dict.values():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return []

    def _flatten_record(item: dict) -> Dict[str, Any]:
        end = item.get("endDate") or {}
        date_str = end.get("fmt") if isinstance(end, dict) else None
        if not date_str:
            raw = end.get("raw") if isinstance(end, dict) else None
            if raw:
                try:
                    date_str = datetime.utcfromtimestamp(int(raw)).strftime("%Y-%m-%d")
                except Exception:
                    date_str = None
        flat = {}
        for k, v in item.items():
            if k in ("maxAge", "endDate"):
                continue
            if isinstance(v, dict):
                flat[k] = v.get("raw", v.get("fmt"))
            else:
                flat[k] = v
        return {"date": date_str, "data": flat}

    def _norm(module_dict: dict) -> List[Dict[str, Any]]:
        out = []
        for it in _to_list(module_dict):
            rec = _flatten_record(it)
            if rec.get("date"):
                out.append(rec)
        return out

    annual_pack = {
        "income": _norm(annual["income"]),
        "balance": _norm(annual["balance"]),
        "cashflow": _norm(annual["cashflow"]),
    }
    quarterly_pack = {
        "income": _norm(quarterly["income"]),
        "balance": _norm(quarterly["balance"]),
        "cashflow": _norm(quarterly["cashflow"]),
    }

    out = {"Annual": annual_pack, "Quarterly": quarterly_pack}

    # Scale to thousands to match UI expectation (Yahoo website shows 'All numbers in thousands')
    if as_thousands:
        def _scale_pack(pack: Dict[str, Any]) -> Dict[str, Any]:
            for stmt in ("income", "balance", "cashflow"):
                rows = pack.get(stmt) or []
                for row in rows:
                    data = row.get("data") or {}
                    for k, v in list(data.items()):
                        try:
                            if isinstance(v, (int, float)) and not isinstance(v, bool):
                                data[k] = v / 1000.0
                        except Exception:
                            pass
            return pack
        out["Annual"] = _scale_pack(out["Annual"])
        out["Quarterly"] = _scale_pack(out["Quarterly"])

    # Compute TTM from quarterly
    if include_ttm:
        try:
            ttm_pack = _compute_ttm_from_quarterly(out["Quarterly"])
            out["TTM"] = ttm_pack
        except Exception:
            pass

    return out

