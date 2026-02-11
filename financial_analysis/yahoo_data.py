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
                            pass
                return acc

            ttm_date = (q_inc[0].get("date") if q_inc else datetime.utcnow().strftime("%Y-%m-%d"))
            out["TTM"] = {
                "income": [{"date": ttm_date, "data": sum_last4(q_inc)}],
                "cashflow": [{"date": ttm_date, "data": sum_last4(q_cf)}] if q_cf else [],
            }
        except Exception:
            # ignore TTM failures
            pass

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


# Alias used by UI
def diagnose_yahoo_quote_summary(symbol: str) -> Dict[str, Any]:
    return diagnose_quote_summary(symbol)

