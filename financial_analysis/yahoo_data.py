import time
from datetime import datetime
import re
import os
import random
import logging
from typing import Dict, List, Any, Optional, Tuple

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


# ==============================
# Provider settings / secrets helpers
# ==============================
def _secret_get(name: str, default=None):
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            return st.secrets.get(name, default)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        return os.getenv(name, default)
    except Exception:
        return default


def _provider_order_financials() -> List[str]:
    """Priority order for statement providers (compliant failover, not bypass).

    Example in secrets: FINANCIALS_PROVIDER_ORDER = "yahoo,eodhd,fmp,alphavantage,argaam,google"
    """
    raw = str(_secret_get("FINANCIALS_PROVIDER_ORDER", "") or "").strip()
    default = ["yahoo", "eodhd", "fmp", "alphavantage", "argaam", "google"]
    if not raw:
        return default
    allow = {"yahoo", "eodhd", "fmp", "alphavantage", "argaam", "google"}
    out = []
    seen = set()
    for part in raw.split(','):
        p = str(part or '').strip().lower()
        if p and p in allow and p not in seen:
            out.append(p); seen.add(p)
    for p in default:
        if p not in seen:
            out.append(p)
    return out


_HTTP_PROVIDER_FAIL_TS: Dict[str, float] = {}
_HTTP_PROVIDER_COOLDOWN_SEC = 30.0


def _generic_http_json(url: str, *, params: Optional[dict] = None, timeout: int = 10, provider: str = "generic", headers: Optional[dict] = None) -> dict:
    """Small resilient JSON getter for external providers (compliant retries/backoff)."""
    if not requests:
        return {}
    provider = str(provider or "generic").lower()
    now = time.time()
    last_fail = float(_HTTP_PROVIDER_FAIL_TS.get(provider, 0.0) or 0.0)
    if last_fail and (now - last_fail) < _HTTP_PROVIDER_COOLDOWN_SEC:
        return {}

    ses = _yf_session() or requests.Session()
    req_headers = {"Accept": "application/json,text/plain,*/*"}
    req_headers.update(headers or {})

    for attempt in range(3):
        try:
            r = ses.get(url, params=params, timeout=timeout, headers=req_headers)
            status = int(getattr(r, 'status_code', 0) or 0)
            txt = (getattr(r, 'text', '') or '').strip()
            if status == 200:
                try:
                    return r.json() or {}
                except Exception:
                    # Some APIs return JSON with text/plain content-type
                    import json
                    return json.loads(txt) if txt else {}

            if status in (429, 500, 502, 503, 504):
                _HTTP_PROVIDER_FAIL_TS[provider] = time.time()
                time.sleep(min(4.0, (0.6 * (2 ** attempt)) + random.uniform(0.0, 0.2)))
                continue

            if status in (401, 403):
                _HTTP_PROVIDER_FAIL_TS[provider] = time.time()
                return {}

            # Non-retryable/unknown
            _HTTP_PROVIDER_FAIL_TS[provider] = time.time()
            return {}
        except Exception:
            _HTTP_PROVIDER_FAIL_TS[provider] = time.time()
            time.sleep(min(3.0, (0.4 * (2 ** attempt)) + random.uniform(0.0, 0.2)))
    return {}


# ==============================


# ==============================
# Throttle (تقليل 429 بسبب إعادة تشغيل Streamlit)
# ==============================
def _yahoo_throttle_wait(url: str):
    """Global throttle to avoid spamming Yahoo endpoints on Streamlit reruns."""
    try:
        if not url:
            return
        key = "quoteSummary" if "quoteSummary" in url else "yahoo_generic"
        min_interval = 15.0 if key == "quoteSummary" else 6.0
        store = st.session_state.get("_yahoo_last_call_ts", {})
        last = float(store.get(key, 0.0) or 0.0)
        now = time.time()
        if last > 0 and (now - last) < min_interval:
            time.sleep(min_interval - (now - last))
        store[key] = time.time()
        st.session_state["_yahoo_last_call_ts"] = store
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:48')

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
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:63')


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
    """
    Robust JSON GET with diagnostics + smarter backoff.

    - Always records diagnostics via _set_last_diag().
    - Adds clear hint for 429/403/404 and other common failures.
    """
    if not requests:
        _set_last_diag(url=url, status=None, error="requests unavailable", snippet=None, hint="requests unavailable")
        return {}

    ses = _yf_session()
    if not ses:
        _set_last_diag(url=url, status=None, error="session unavailable", snippet=None, hint="session unavailable")
        return {}

    last_status = None
    last_snippet = None
    last_err = None

    _yahoo_throttle_wait(url)

    for i in range(retries + 1):
        try:
            r = ses.get(url, timeout=timeout)
            last_status = getattr(r, "status_code", None)
            txt = (getattr(r, "text", "") or "")
            last_snippet = txt[:200].replace("\n", " ").strip() if txt else None

            if last_status == 200:
                try:
                    data = r.json() or {}
                    _set_last_diag(url=url, status=200, error=None, snippet=last_snippet, hint="OK")
                    return data
                except Exception as e:
                    last_err = e
                    _set_last_diag(url=url, status=200, error=e, snippet=last_snippet, hint="Invalid JSON response")
                    return {}

            # Non-200: set useful hint
            if last_status == 429:
                _set_last_diag(
                    url=url,
                    status=429,
                    error=None,
                    snippet=last_snippet,
                    hint="Rate limit (429) — انتظر 1-2 دقيقة ثم أعد المحاولة",
                )
                # exponential backoff
                time.sleep(max(0.5, sleep) * (2 ** i))
                continue

            if last_status in (401, 403):
                _set_last_diag(
                    url=url,
                    status=last_status,
                    error=None,
                    snippet=last_snippet,
                    hint="Blocked/Forbidden — جرّب لاحقًا أو استخدم مصدر بديل",
                )
                # no aggressive retry on forbidden
                return {}

            if last_status == 404:
                _set_last_diag(
                    url=url,
                    status=404,
                    error=None,
                    snippet=last_snippet,
                    hint="Not found — رمز غير صحيح أو تغيّر endpoint",
                )
                return {}

            if last_status in (503, 502, 500):
                _set_last_diag(
                    url=url,
                    status=last_status,
                    error=None,
                    snippet=last_snippet,
                    hint="Server busy — أعد المحاولة لاحقًا",
                )
                time.sleep(max(0.5, sleep) * (1.5 ** i))
                continue

            _set_last_diag(
                url=url,
                status=last_status,
                error=None,
                snippet=last_snippet,
                hint=f"HTTP {last_status} — استجابة غير متوقعة",
            )

        except Exception as e:
            last_err = e
            _set_last_diag(url=url, status=last_status, error=e, snippet=last_snippet, hint="Network/timeout error")

        if i < retries:
            time.sleep(max(0.2, sleep))

    # Final fallback
    if last_status == 429:
        hint = "Rate limit (429) — انتظر 1-2 دقيقة ثم أعد المحاولة"
    elif last_status in (401, 403):
        hint = "Blocked/Forbidden — جرّب لاحقًا أو استخدم مصدر بديل"
    elif last_status == 404:
        hint = "Not found — رمز غير صحيح أو تغيّر endpoint"
    else:
        hint = "Empty response"

    _set_last_diag(url=url, status=last_status, error=last_err, snippet=last_snippet, hint=hint)
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
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:273')
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
# ==============================================================
# ✅ Unified Financial Statements (DB cache + Yahoo JSON + fallback)
#
# ملاحظة مهمة: بعض الواجهات كانت تمرر الرمز بصيغة "SR.1150".
# هذا كان يؤدي لتوحيد خاطئ مثل "SR.1150.SR" وبالتالي عدم مطابقة الرموز
# المخزنة في قاعدة البيانات (مثال: "1150.SR").
# لذلك نُطبّع الرمز *قبل* الكاش حتى لا تتكرر مفاتيح الكاش لنفس السهم.
# ==============================================================

def get_financial_statements(symbol: str, period_type: str = "Annual", refresh: bool = False) -> pd.DataFrame:
    sym = get_ticker_symbol(symbol)
    ptype = str(period_type or "Annual").strip().title()
    if ptype not in ("Annual", "Quarterly"):
        ptype = "Annual"
    return _get_financial_statements_cached(sym, ptype, bool(refresh))


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)  # 6 hours
def _get_financial_statements_cached(sym: str, ptype: str = "Annual", refresh: bool = False) -> pd.DataFrame:
    """يرجع DataFrame موحّد من جدول financialstatements.

    - sym/ptype هنا يفترض أنها *مطبّعة*.
    - لو refresh=False: يرجع المخزن إن وجد (سريع)
    - لو refresh=True أو لا يوجد مخزن: يحاول Yahoo JSON ثم بدائل
    """
    from .store import get_stored_financials_df, save_financial_record
    from .parsers import fetch_financials_from_argaam, fetch_financials_from_google_finance

    stored = get_stored_financials_df(sym, ptype)
    if (not refresh) and (stored is not None) and (not stored.empty):
        return stored

    records = fetch_financial_statements_multi_source(sym, ptype)

    if not records and ptype == "Annual":
        try:
            d = fetch_financials_from_argaam(sym) or {}
            if d:
                records = [{"date": d.get("date") or datetime.now().strftime("%Y-12-31"), "data": d}]
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:457')

    if not records and ptype == "Annual":
        try:
            d2 = fetch_financials_from_google_finance(sym) or {}
            if d2:
                records = [{"date": d2.get("date") or datetime.now().strftime("%Y-12-31"), "data": d2}]
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:465')

    if records:
        for rec in records:
            d = rec.get("date")
            data = rec.get("data", {}) or {}
            save_financial_record(
                sym,
                d,
                data,
                period_type=ptype,
                source=(rec.get("_source") if isinstance(rec, dict) else None) or ("YahooJSON" if isinstance(data, dict) and "revenue" in data else "External"),
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
            # keep whatever hint set by _http_get_json; fallback only if missing
            diag["hint"] = diag.get("hint") or "Empty response"
        return diag
    except Exception as e:
        diag = get_last_yahoo_diagnostics()
        diag["error"] = str(e)
        status = diag.get("status")
        if status == 429:
            diag["hint"] = "Rate limit (429) — حاول بعد 1-2 دقيقة أو فعّل التخزين المحلي"
        elif status in (401, 403):
            diag["hint"] = "Blocked/Forbidden — جرّب لاحقًا أو استخدم مصدر بديل"
        elif status == 404:
            diag["hint"] = "Symbol not found / endpoint changed"
        return diag


# ==============================================================
# 📦 Full Statements (ALL line-items) via QuoteSummary
# ==============================================================
_FULL_QS_CACHE = {}  # key -> (ts, data)
_FULL_QS_TTL_SEC = 12 * 60 * 60  # 12h


def _qs_cached(symbol: str, modules: List[str]) -> dict:
    """
    Cached wrapper around _yahoo_quote_summary to reduce repeated hits (Streamlit reruns).
    Cache is process-local (in-memory).
    """
    key = f"{get_ticker_symbol(symbol)}::" + ",".join(modules or [])
    now = time.time()
    ts, data = _FULL_QS_CACHE.get(key, (0.0, None))
    if data is not None and ts and (now - ts) < _FULL_QS_TTL_SEC:
        return data
    data = _yahoo_quote_summary(symbol, modules=modules) or {}
    # Cache even empty response for a short time to avoid hammering on 429
    _FULL_QS_CACHE[key] = (now, data)
    return data


def _flatten_stmt_item(item: dict, as_thousands: bool = True) -> Dict[str, float]:
    """
    Convert a single Yahoo statement dict to {line_item: value} with safe raw extraction.
    """
    out: Dict[str, float] = {}
    if not isinstance(item, dict):
        return out
    for k, v in item.items():
        if k in ("endDate", "maxAge", "periodType"):
            continue
        # Values often like {"raw":123,"fmt":"123"}
        val = _yf_raw(v, default=0.0)
        if as_thousands:
            val = val / 1000.0
        out[str(k)] = float(val)
    return out


def fetch_full_financial_statements_yahoo_json(
    symbol: str,
    period_type: str = "All",
    *,
    as_thousands: bool = True,
    include_ttm: bool = True,
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Fetch and return *all* line-items for Income/Balance/Cashflow statements.

    Returns:
      {
        "Annual": {"income": [{"date": "...", "data": {...}}, ...],
                   "balance": [...],
                   "cashflow": [...]},
        "Quarterly": {...},
        "TTM": {"income":[...], "cashflow":[...]}  # derived from Quarterly (optional)
      }

    Notes:
    - Uses QuoteSummary modules which can be rate-limited (429). We cache per-process.
    - If Yahoo blocks, returns {} and diagnostics can be read via get_last_yahoo_diagnostics().
    """
    sym = get_ticker_symbol(symbol)
    if not sym:
        return {}

    period_norm = (period_type or "All").strip().lower()
    want_a = period_norm in ("all", "annual", "a", "year", "yearly")
    want_q = period_norm in ("all", "quarterly", "q", "quarter", "quarters")

    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    # Annual
    if want_a:
        mods = ["incomeStatementHistory", "balanceSheetHistory", "cashflowStatementHistory"]
        root = _qs_cached(sym, mods)
        if root:
            inc = _extract_stmt_list(root, "incomeStatementHistory")
            bal = _extract_stmt_list(root, "balanceSheetHistory")
            cf = _extract_stmt_list(root, "cashflowStatementHistory")

            out["Annual"] = {
                "income": [{"date": _yf_date_str(x.get("endDate")), "data": _flatten_stmt_item(x, as_thousands)} for x in inc or []],
                "balance": [{"date": _yf_date_str(x.get("endDate")), "data": _flatten_stmt_item(x, as_thousands)} for x in bal or []],
                "cashflow": [{"date": _yf_date_str(x.get("endDate")), "data": _flatten_stmt_item(x, as_thousands)} for x in cf or []],
            }

    # Quarterly
    if want_q:
        mods = ["incomeStatementHistoryQuarterly", "balanceSheetHistoryQuarterly", "cashflowStatementHistoryQuarterly"]
        root = _qs_cached(sym, mods)
        if root:
            inc = _extract_stmt_list(root, "incomeStatementHistoryQuarterly")
            bal = _extract_stmt_list(root, "balanceSheetHistoryQuarterly")
            cf = _extract_stmt_list(root, "cashflowStatementHistoryQuarterly")

            out["Quarterly"] = {
                "income": [{"date": _yf_date_str(x.get("endDate")), "data": _flatten_stmt_item(x, as_thousands)} for x in inc or []],
                "balance": [{"date": _yf_date_str(x.get("endDate")), "data": _flatten_stmt_item(x, as_thousands)} for x in bal or []],
                "cashflow": [{"date": _yf_date_str(x.get("endDate")), "data": _flatten_stmt_item(x, as_thousands)} for x in cf or []],
            }

    # Derive TTM from quarterly income/cashflow (best-effort)
    if include_ttm and "Quarterly" in out and out["Quarterly"].get("income"):
        try:
            q_inc = out["Quarterly"]["income"][:4]
            q_cf = out["Quarterly"]["cashflow"][:4] if out["Quarterly"].get("cashflow") else []

            def sum_last4(recs: List[Dict[str, Any]]) -> Dict[str, float]:
                acc: Dict[str, float] = {}
                for r in recs or []:
                    d = (r or {}).get("data") or {}
                    for k, v in d.items():
                        try:
                            acc[k] = float(acc.get(k, 0.0) + float(v or 0.0))
                        except Exception:
                            import logging
                            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:626')
                return acc

            ttm_date = (q_inc[0].get("date") if q_inc else datetime.utcnow().strftime("%Y-%m-%d"))
            out["TTM"] = {
                "income": [{"date": ttm_date, "data": sum_last4(q_inc)}],
                "cashflow": [{"date": ttm_date, "data": sum_last4(q_cf)}] if q_cf else [],
            }
        except Exception:
            # ignore TTM failures
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/yahoo_data.py:635')

    # Remove empty
    out = {k: v for k, v in out.items() if v and any((v.get("income") or v.get("balance") or v.get("cashflow")))}
    return out


def fetch_full_financial_statements_yahoo_html(*args, **kwargs) -> Dict[str, Any]:
    """
    HTML fallback placeholder.
    بعض البيئات تُحظر JSON (429) لكن تسمح HTML. إذا احتجنا لاحقًا،
    نضيف scraper خفيف هنا. حاليًا نرجع {} بشكل آمن.
    """
    return {}


# ==============================================================
# 🌐 External API Providers (official/paid-friendly fallbacks)
# ==============================================================
def _period_norm(period_type: str = "All") -> str:
    p = str(period_type or "All").strip().lower()
    if p in ("annual", "a", "year", "yearly"):
        return "Annual"
    if p in ("quarterly", "q", "quarter"):
        return "Quarterly"
    return "All"


def _trim_periods(period_type: str, annual: List[dict], quarterly: List[dict]) -> Tuple[List[dict], List[dict]]:
    pn = _period_norm(period_type)
    if pn == "Annual":
        return annual or [], []
    if pn == "Quarterly":
        return [], quarterly or []
    return annual or [], quarterly or []


def _safe_num(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        if isinstance(v, dict):
            return _yf_raw(v, default)
        return float(str(v).replace(',', '').strip())
    except Exception:
        return float(default)


def _map_summary_fields(stmt_kind: str, row: dict) -> dict:
    d = row or {}
    k = (stmt_kind or '').lower()
    if k == 'income':
        return {
            'revenue': _safe_num(d.get('revenue') or d.get('totalRevenue') or d.get('total_revenue')),
            'net_income': _safe_num(d.get('netIncome') or d.get('net_income') or d.get('netIncomeApplicableToCommonShares')),
        }
    if k == 'balance':
        return {
            'total_assets': _safe_num(d.get('totalAssets') or d.get('total_assets')),
            'total_liabilities': _safe_num(d.get('totalLiabilities') or d.get('totalLiab') or d.get('total_liabilities')),
            'total_equity': _safe_num(d.get('totalStockholdersEquity') or d.get('totalStockholderEquity') or d.get('total_equity') or d.get('totalShareholderEquity')),
            'current_assets': _safe_num(d.get('totalCurrentAssets') or d.get('currentAssets') or d.get('total_current_assets')),
            'current_liabilities': _safe_num(d.get('totalCurrentLiabilities') or d.get('currentLiabilities') or d.get('total_current_liabilities')),
            'long_term_debt': _safe_num(d.get('longTermDebt') or d.get('long_term_debt') or d.get('longTermDebtNoncurrent')),
        }
    if k == 'cashflow':
        return {
            'operating_cash_flow': _safe_num(d.get('operatingCashFlow') or d.get('operatingCashflow') or d.get('totalCashFromOperatingActivities') or d.get('netCashProvidedByOperatingActivities')),
        }
    return {}


def _merge_summary_from_full_bundle(bundle: Dict[str, Dict[str, List[Dict[str, Any]]]], period_type: str = 'Annual') -> List[Dict[str, Any]]:
    pn = _period_norm(period_type)
    target = bundle.get(pn) or {}
    if not target:
        return []
    by_date: Dict[str, Dict[str, Any]] = {}
    src_by_date: Dict[str, str] = {}
    for kind in ('income', 'balance', 'cashflow'):
        for rec in (target.get(kind) or []):
            d = str((rec or {}).get('date') or '').strip()
            payload = (rec or {}).get('data') or {}
            if not d or not isinstance(payload, dict):
                continue
            row = by_date.setdefault(d, {})
            row.update(_map_summary_fields(kind, payload))
            src = str((rec or {}).get('_source') or '')
            if src:
                src_by_date[d] = src

    out = []
    for d in sorted(by_date.keys(), reverse=True):
        row = by_date[d]
        keys = ['revenue','net_income','total_assets','total_liabilities','total_equity','operating_cash_flow','current_assets','current_liabilities','long_term_debt']
        data = {k: float(row.get(k, 0.0) or 0.0) for k in keys}
        if sum(abs(v) for v in data.values()) <= 0:
            continue
        out.append({'date': d, 'data': data, '_source': src_by_date.get(d)})
    return out


def _to_thousands(data: dict, as_thousands: bool) -> dict:
    out = {}
    for k, v in (data or {}).items():
        try:
            val = _safe_num(v, 0.0)
            out[str(k)] = (val / 1000.0) if as_thousands else val
        except Exception:
            continue
    return out


def _normalize_fmp_records(recs: List[dict], as_thousands: bool = True, source: str = 'FMP') -> List[Dict[str, Any]]:
    out = []
    for r in (recs or []):
        if not isinstance(r, dict):
            continue
        d = _safe_date_str(r.get('date') or r.get('fillingDate') or r.get('acceptedDate'))
        payload = {k: v for k, v in r.items() if k not in ('symbol','reportedCurrency','cik','calendarYear','period','link','finalLink','acceptedDate')}
        if not payload:
            continue
        out.append({'date': d, 'data': _to_thousands(payload, as_thousands), '_source': source})
    return out


def _normalize_alphavantage_records(recs: List[dict], as_thousands: bool = True, source: str = 'AlphaVantage') -> List[Dict[str, Any]]:
    out = []
    for r in (recs or []):
        if not isinstance(r, dict):
            continue
        d = _safe_date_str(r.get('fiscalDateEnding') or r.get('reportedDate'))
        payload = {k: v for k, v in r.items() if k not in ('fiscalDateEnding','reportedCurrency')}
        if not payload:
            continue
        out.append({'date': d, 'data': _to_thousands(payload, as_thousands), '_source': source})
    return out


def _normalize_eodhd_section(sec: dict, as_thousands: bool = True, source: str = 'EODHD') -> Tuple[List[dict], List[dict]]:
    """Normalize EODHD section in either array-form or dict-of-date form."""
    def _iter_rows(container):
        if isinstance(container, list):
            for x in container:
                if isinstance(x, dict):
                    yield x
        elif isinstance(container, dict):
            for d, payload in container.items():
                if isinstance(payload, dict):
                    row = dict(payload)
                    row.setdefault('date', d)
                    yield row

    yearly = list(_iter_rows((sec or {}).get('yearly') or (sec or {}).get('annual')))
    quarterly = list(_iter_rows((sec or {}).get('quarterly')))
    return _normalize_fmp_records(yearly, as_thousands=as_thousands, source=source), _normalize_fmp_records(quarterly, as_thousands=as_thousands, source=source)


def _attach_ttm(bundle: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    if 'Quarterly' not in bundle:
        return bundle
    q = bundle.get('Quarterly') or {}
    q_inc = (q.get('income') or [])[:4]
    q_cf = (q.get('cashflow') or [])[:4]
    if not q_inc:
        return bundle
    def _sum4(recs):
        acc = {}
        src = None
        for rec in recs:
            src = src or rec.get('_source')
            for k, v in ((rec or {}).get('data') or {}).items():
                try:
                    acc[k] = float(acc.get(k, 0.0) + float(v or 0.0))
                except Exception:
                    continue
        return acc, src
    ttm_date = str(q_inc[0].get('date') or datetime.utcnow().strftime('%Y-%m-%d'))
    inc_sum, src_i = _sum4(q_inc)
    cf_sum, src_c = _sum4(q_cf) if q_cf else ({}, None)
    ttm = {'income': [{ 'date': ttm_date, 'data': inc_sum, '_source': src_i }] if inc_sum else []}
    if cf_sum:
        ttm['cashflow'] = [{ 'date': ttm_date, 'data': cf_sum, '_source': src_c }]
    if ttm.get('income') or ttm.get('cashflow'):
        bundle['TTM'] = ttm
    return bundle


def _build_bundle(annual_income=None, annual_balance=None, annual_cash=None, q_income=None, q_balance=None, q_cash=None, include_ttm: bool = True) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    if annual_income or annual_balance or annual_cash:
        out['Annual'] = {'income': annual_income or [], 'balance': annual_balance or [], 'cashflow': annual_cash or []}
    if q_income or q_balance or q_cash:
        out['Quarterly'] = {'income': q_income or [], 'balance': q_balance or [], 'cashflow': q_cash or []}
    if include_ttm:
        out = _attach_ttm(out)
    return {k: v for k, v in out.items() if v and any(v.get(x) for x in ('income','balance','cashflow'))}


def _fetch_full_fmp(symbol: str, period_type: str = 'All', *, as_thousands: bool = True, include_ttm: bool = True) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    key = str(_secret_get('FMP_API_KEY', '') or '').strip()
    if not key or not requests:
        return {}
    sym = get_ticker_symbol(symbol)
    base = 'https://financialmodelingprep.com/api/v3'
    pn = _period_norm(period_type)

    def _one(path: str, period: str):
        url = f"{base}/{path}/{sym}"
        data = _generic_http_json(url, params={'period': period, 'limit': 8, 'apikey': key}, provider='fmp')
        return data if isinstance(data, list) else []

    a = q = None
    if pn in ('All','Annual'):
        a = {
            'income': _normalize_fmp_records(_one('income-statement', 'annual'), as_thousands, 'FMP'),
            'balance': _normalize_fmp_records(_one('balance-sheet-statement', 'annual'), as_thousands, 'FMP'),
            'cashflow': _normalize_fmp_records(_one('cash-flow-statement', 'annual'), as_thousands, 'FMP'),
        }
    if pn in ('All','Quarterly'):
        q = {
            'income': _normalize_fmp_records(_one('income-statement', 'quarter'), as_thousands, 'FMP'),
            'balance': _normalize_fmp_records(_one('balance-sheet-statement', 'quarter'), as_thousands, 'FMP'),
            'cashflow': _normalize_fmp_records(_one('cash-flow-statement', 'quarter'), as_thousands, 'FMP'),
        }
    return _build_bundle(
        annual_income=(a or {}).get('income'), annual_balance=(a or {}).get('balance'), annual_cash=(a or {}).get('cashflow'),
        q_income=(q or {}).get('income'), q_balance=(q or {}).get('balance'), q_cash=(q or {}).get('cashflow'),
        include_ttm=include_ttm,
    )


def _fetch_full_alphavantage(symbol: str, period_type: str = 'All', *, as_thousands: bool = True, include_ttm: bool = True) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    key = str(_secret_get('ALPHAVANTAGE_API_KEY', '') or '').strip()
    if not key or not requests:
        return {}
    sym = get_ticker_symbol(symbol)
    pn = _period_norm(period_type)
    base = 'https://www.alphavantage.co/query'
    fn_map = [('income','INCOME_STATEMENT'), ('balance','BALANCE_SHEET'), ('cashflow','CASH_FLOW')]
    annual = {}
    quarterly = {}
    for label, fn in fn_map:
        data = _generic_http_json(base, params={'function': fn, 'symbol': sym, 'apikey': key}, provider='alphavantage')
        if not isinstance(data, dict) or data.get('Note') or data.get('Information'):
            return {}
        if pn in ('All','Annual'):
            annual[label] = _normalize_alphavantage_records(data.get('annualReports') or [], as_thousands, 'AlphaVantage')
        if pn in ('All','Quarterly'):
            quarterly[label] = _normalize_alphavantage_records(data.get('quarterlyReports') or [], as_thousands, 'AlphaVantage')
    return _build_bundle(
        annual_income=annual.get('income'), annual_balance=annual.get('balance'), annual_cash=annual.get('cashflow'),
        q_income=quarterly.get('income'), q_balance=quarterly.get('balance'), q_cash=quarterly.get('cashflow'),
        include_ttm=include_ttm,
    )


def _fetch_full_eodhd(symbol: str, period_type: str = 'All', *, as_thousands: bool = True, include_ttm: bool = True) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    key = str(_secret_get('EODHD_API_KEY', '') or '').strip()
    if not key or not requests:
        return {}
    sym = get_ticker_symbol(symbol)
    url = f'https://eodhistoricaldata.com/api/fundamentals/{sym}'
    data = _generic_http_json(url, params={'api_token': key, 'fmt': 'json'}, provider='eodhd', timeout=14)
    if not isinstance(data, dict) or not data:
        return {}
    fin = (data.get('Financials') or {}) if isinstance(data, dict) else {}
    inc_a, inc_q = _normalize_eodhd_section(fin.get('Income_Statement') or fin.get('IncomeStatement') or {}, as_thousands, 'EODHD')
    bs_a, bs_q = _normalize_eodhd_section(fin.get('Balance_Sheet') or fin.get('BalanceSheet') or {}, as_thousands, 'EODHD')
    cf_a, cf_q = _normalize_eodhd_section(fin.get('Cash_Flow') or fin.get('CashFlow') or {}, as_thousands, 'EODHD')
    inc_a, inc_q = _trim_periods(period_type, inc_a, inc_q)
    bs_a, bs_q = _trim_periods(period_type, bs_a, bs_q)
    cf_a, cf_q = _trim_periods(period_type, cf_a, cf_q)
    return _build_bundle(annual_income=inc_a, annual_balance=bs_a, annual_cash=cf_a, q_income=inc_q, q_balance=bs_q, q_cash=cf_q, include_ttm=include_ttm)


def fetch_full_financial_statements_multi_source(symbol: str, period_type: str = 'All', *, as_thousands: bool = True, include_ttm: bool = True) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Try Yahoo first, then configured API providers (EODHD/FMP/AlphaVantage).

    This is a *compliant failover* approach (cache + backoff + alternate providers),
    not a mechanism to bypass website protections.
    """
    order = _provider_order_financials()
    for provider in order:
        try:
            if provider == 'yahoo':
                bundle = fetch_full_financial_statements_yahoo_json(symbol, period_type=period_type, as_thousands=as_thousands, include_ttm=include_ttm) or {}
            elif provider == 'eodhd':
                bundle = _fetch_full_eodhd(symbol, period_type=period_type, as_thousands=as_thousands, include_ttm=include_ttm) or {}
            elif provider == 'fmp':
                bundle = _fetch_full_fmp(symbol, period_type=period_type, as_thousands=as_thousands, include_ttm=include_ttm) or {}
            elif provider == 'alphavantage':
                bundle = _fetch_full_alphavantage(symbol, period_type=period_type, as_thousands=as_thousands, include_ttm=include_ttm) or {}
            else:
                bundle = {}
            if isinstance(bundle, dict) and bundle:
                return bundle
        except Exception:
            logging.getLogger(__name__).exception('Provider failed: %s', provider)
            continue
    return {}


def fetch_financial_statements_multi_source(symbol: str, period_type: str = 'Annual') -> List[Dict[str, Any]]:
    """Summary statements records with provider failover.

    Order: Yahoo -> API providers (via full bundle collapse) -> Argaam -> Google Finance (best-effort HTML).
    """
    sym = get_ticker_symbol(symbol)
    ptype = _period_norm(period_type)
    if ptype == 'All':
        ptype = 'Annual'

    # 1) Yahoo first (fast, already normalized)
    recs = fetch_financial_statements_yahoo_json(sym, ptype)
    if recs:
        for r in recs:
            if isinstance(r, dict):
                r.setdefault('_source', 'YahooJSON')
        return recs

    # 2) API providers via full-bundle normalization
    bundle = fetch_full_financial_statements_multi_source(sym, period_type=ptype, as_thousands=False, include_ttm=False)
    recs = _merge_summary_from_full_bundle(bundle, period_type=ptype)
    if recs:
        return recs

    # 3) HTML best-effort fallbacks (annual only)
    if ptype == 'Annual':
        try:
            from .parsers import fetch_financials_from_argaam, fetch_financials_from_google_finance
            d = fetch_financials_from_argaam(sym) or {}
            if d:
                return [{'date': d.get('date') or datetime.now().strftime('%Y-12-31'), 'data': d, '_source': 'Argaam'}]
            d2 = fetch_financials_from_google_finance(sym) or {}
            if d2:
                return [{'date': d2.get('date') or datetime.now().strftime('%Y-12-31'), 'data': d2, '_source': 'GoogleFinance'}]
        except Exception:
            pass

    return []


# Alias used by UI
def diagnose_yahoo_quote_summary(symbol: str) -> Dict[str, Any]:
    return diagnose_quote_summary(symbol)

