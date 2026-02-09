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
def _yahoo_extract_raw(v):
    """Extract numeric raw values from Yahoo dicts."""
    try:
        if isinstance(v, dict):
            if 'raw' in v and isinstance(v['raw'], (int, float)):
                return float(v['raw'])
            if 'fmt' in v and isinstance(v.get('fmt'), (int, float)):
                return float(v['fmt'])
        if isinstance(v, (int, float)):
            return float(v)
    except Exception:
        return None
    return None


def _yahoo_extract_date(item: dict):
    """Best-effort extract a date string from Yahoo statement row."""
    for k in ('endDate', 'asOfDate', 'date'):
        v = (item or {}).get(k)
        if isinstance(v, dict):
            # prefer fmt (YYYY-MM-DD) if present
            if isinstance(v.get('fmt'), str) and v.get('fmt'):
                return v['fmt']
            raw = v.get('raw')
            if isinstance(raw, (int, float)):
                try:
                    from datetime import datetime
                    return datetime.utcfromtimestamp(int(raw)).strftime('%Y-%m-%d')
                except Exception:
                    pass
        if isinstance(v, str) and v:
            return v
    return None


def _yahoo_statement_records(history_container: dict, list_key: str, *, as_thousands: bool = False):
    lst = (history_container or {}).get(list_key) or []
    out = []
    for item in lst:
        if not isinstance(item, dict):
            continue
        d = _yahoo_extract_date(item)
        if not d:
            continue
        data = {}
        for k, v in item.items():
            if k in ('maxAge', 'endDate', 'asOfDate', 'periodType', 'currencyCode'):
                continue
            raw = _yahoo_extract_raw(v)
            if raw is None:
                continue
            if as_thousands:
                raw = raw / 1000.0
            data[k] = raw
        if data:
            out.append({'date': d, 'data': data})
    return out


def _compute_ttm(quarterly_recs, kind: str):
    """Compute a light TTM bundle.
    - income/cash: sum last 4 quarters
    - balance: most recent quarter
    """
    if not quarterly_recs:
        return []
    # sort by date desc
    qr = sorted([r for r in quarterly_recs if isinstance(r, dict) and r.get('date')], key=lambda r: r['date'], reverse=True)
    if not qr:
        return []
    if kind == 'balance':
        return [qr[0]]
    window = qr[:4]
    agg = {}
    for r in window:
        dct = (r.get('data') or {})
        for k, v in dct.items():
            if isinstance(v, (int, float)):
                agg[k] = agg.get(k, 0.0) + float(v)
    return [{'date': qr[0]['date'], 'data': agg}] if agg else []


def fetch_full_financial_statements_yahoo_json(
    symbol: str,
    period: str = "annual",
    *,
    period_type: str | None = None,
    as_thousands: bool = False,
    include_ttm: bool = False,
) -> Dict[str, Any]:
    """Fetch full financial statements from Yahoo (quoteSummary).

    This function supports **two** calling styles for backward compatibility:

    1) Legacy/raw style (existing callers):
       fetch_full_financial_statements_yahoo_json(symbol, period="annual"|"quarterly")
       -> returns a raw dict with keys: income, balance, cash, meta

    2) Structured/full style (used by sync_full_yahoo):
       fetch_full_financial_statements_yahoo_json(
           symbol,
           period_type="Annual"|"Quarterly"|"All",
           as_thousands=True,
           include_ttm=True,
       )
       -> returns dict: {"Annual": {"income": [...], "balance": [...], "cash": [...]}, ...}

    Always returns an empty dict on failure.
    """

    symbol = get_ticker_symbol(symbol)

    # ---------------------------
    # Helpers
    # ---------------------------
    def _extract_raw(v):
        if isinstance(v, dict):
            if "raw" in v:
                return v.get("raw")
            if "fmt" in v:
                return v.get("fmt")
        return v

    def _coerce_date(v) -> str | None:
        v = _extract_raw(v)
        if v is None:
            return None
        # unix timestamp
        if isinstance(v, (int, float)):
            try:
                return datetime.utcfromtimestamp(float(v)).date().isoformat()
            except Exception:
                return None
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            # already ISO or formatted; keep as-is
            return s
        return None

    def _to_number(v):
        v = _extract_raw(v)
        if isinstance(v, (int, float)):
            x = float(v)
            if as_thousands:
                x = x / 1000.0
            return x
        return None

    def _history_to_records(container: dict | None, list_key: str) -> list[dict]:
        container = container or {}
        items = container.get(list_key) or []
        recs: list[dict] = []
        if not isinstance(items, list):
            return recs
        for it in items:
            if not isinstance(it, dict):
                continue
            date = _coerce_date(it.get("endDate") or it.get("asOfDate") or it.get("periodEndingDate"))
            if not date:
                continue
            data: dict[str, float] = {}
            for k, v in it.items():
                if k in ("maxAge", "endDate", "asOfDate", "periodType", "currencyCode"):
                    continue
                num = _to_number(v)
                if num is None:
                    continue
                data[str(k)] = num
            if data:
                recs.append({"date": date, "data": data})
        return recs

    def _build_bundle(payload: dict, p: str) -> dict[str, list[dict]]:
        is_q = p.startswith("q")
        inc_key = "incomeStatementHistoryQuarterly" if is_q else "incomeStatementHistory"
        bs_key = "balanceSheetHistoryQuarterly" if is_q else "balanceSheetHistory"
        cf_key = "cashflowStatementHistoryQuarterly" if is_q else "cashflowStatementHistory"

        income = _history_to_records(payload.get(inc_key) or {}, "incomeStatementHistory")
        balance = _history_to_records(payload.get(bs_key) or {}, "balanceSheetStatements")
        cash = _history_to_records(payload.get(cf_key) or {}, "cashflowStatements")
        return {"income": income, "balance": balance, "cash": cash}

    def _compute_ttm_from_quarterly(q_bundle: dict[str, list[dict]]) -> dict[str, list[dict]]:
        # income + cash: sum latest 4 quarters; balance: latest quarter snapshot
        def sum_latest4(recs: list[dict]) -> dict[str, float]:
            out: dict[str, float] = {}
            top = recs[:4]
            for r in top:
                d = (r or {}).get("data") or {}
                if not isinstance(d, dict):
                    continue
                for k, v in d.items():
                    try:
                        out[k] = float(out.get(k, 0.0)) + float(v)
                    except Exception:
                        continue
            return out

        def latest_snapshot(recs: list[dict]) -> dict[str, float]:
            if not recs:
                return {}
            d = (recs[0] or {}).get("data") or {}
            return {str(k): float(v) for k, v in d.items() if isinstance(v, (int, float))}

        inc = q_bundle.get("income") or []
        bal = q_bundle.get("balance") or []
        cf = q_bundle.get("cash") or []
        date = None
        if inc and isinstance(inc[0], dict):
            date = inc[0].get("date")
        date = date or (bal[0].get("date") if bal and isinstance(bal[0], dict) else None) or (cf[0].get("date") if cf and isinstance(cf[0], dict) else None)
        if not date:
            return {"income": [], "balance": [], "cash": []}

        ttm_income = sum_latest4(inc)
        ttm_cash = sum_latest4(cf)
        ttm_balance = latest_snapshot(bal)

        out = {
            "income": [{"date": str(date), "data": ttm_income}] if ttm_income else [],
            "cash": [{"date": str(date), "data": ttm_cash}] if ttm_cash else [],
            "balance": [{"date": str(date), "data": ttm_balance}] if ttm_balance else [],
        }
        return out

    # ---------------------------
    # Fetch quoteSummary
    # ---------------------------
    try:
        modules = [
            "incomeStatementHistory",
            "incomeStatementHistoryQuarterly",
            "balanceSheetHistory",
            "balanceSheetHistoryQuarterly",
            "cashflowStatementHistory",
            "cashflowStatementHistoryQuarterly",
        ]
        raw = _yahoo_quote_summary(symbol, modules=modules) or {}
        result = (raw.get("quoteSummary", {}) or {}).get("result") or []
        if not result:
            return {}
        payload = result[0] or {}

        # Legacy/raw style
        if period_type is None:
            p = (period or "annual").lower()
            bundle = _build_bundle(payload, p)
            out = {"meta": {"symbol": symbol, "period": p}}
            out.update(bundle)
            return out

        # Structured/full style
        pt = (period_type or "All").strip().lower()
        out: Dict[str, Any] = {}
        if pt in ("all", "both"):
            out["Annual"] = _build_bundle(payload, "annual")
            out["Quarterly"] = _build_bundle(payload, "quarterly")
            if include_ttm:
                out["TTM"] = _compute_ttm_from_quarterly(out.get("Quarterly") or {})
        elif pt.startswith("q"):
            out["Quarterly"] = _build_bundle(payload, "quarterly")
            if include_ttm:
                out["TTM"] = _compute_ttm_from_quarterly(out.get("Quarterly") or {})
        else:
            out["Annual"] = _build_bundle(payload, "annual")
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
