# financial_analysis/sync.py
from typing import Tuple, List

import yfinance as yf
import pandas as pd

from market_data import get_ticker_symbol
from .store import save_financial_record
from .store import save_full_statement_record, ensure_financialstatements_raw_table
from .utils import _safe_float, _safe_date_str
from .parsers import fetch_financials_from_argaam, fetch_financials_from_google_finance


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
            dt = d.get("date") or _safe_date_str(symbol)  # (كما هو best-effort)
            if save_financial_record(symbol, dt, d, "Annual", "Argaam"):
                saved += 1
                notes.append("تمت المحاولة من أرقام")
    except Exception as e:
        notes.append(f"أرقام فشل: {e}")

    if saved == 0:
        try:
            d2 = fetch_financials_from_google_finance(symbol) or {}
            if isinstance(d2, dict) and d2:
                dt = d2.get("date") or _safe_date_str(symbol)
                if save_financial_record(symbol, dt, d2, "Annual", "GoogleFinance"):
                    saved += 1
                    notes.append("تمت المحاولة من Google Finance")
        except Exception as e:
            notes.append(f"Google Finance فشل: {e}")

    if saved > 0:
        return True, f"تم حفظ {saved} سجل من بدائل Yahoo. " + " | ".join(notes)
    return False, "لم تنجح البدائل. " + (" | ".join(notes) if notes else "")
# ==============================================================
# 🧾 Full Statements Helpers (Income/Balance/Cashflow)
# ==============================================================
def _df_to_dict_for_date(df, d) -> dict:
    """Convert a yfinance statement DataFrame column into a dict of {line_item: value}."""
    out = {}
    if df is None or getattr(df, "empty", True):
        return out
    try:
        if d not in df.columns:
            return out
        col = df[d]
        # df index are line item names
        for k, v in col.items():
            try:
                if pd.isna(v):
                    continue
            except Exception:
                pass
            try:
                out[str(k)] = float(v)
            except Exception:
                try:
                    out[str(k)] = float(_safe_float(v))
                except Exception:
                    continue
    except Exception:
        return {}
    return out


def _save_full_pack(symbol: str, fin, bs, cf, p_type: str, source: str = "yfinance"):
    """Save full statements raw + thousands for available dates."""
    symbol = get_ticker_symbol(symbol)
    try:
        fin_cols = set(getattr(fin, "columns", []) or [])
        bs_cols = set(getattr(bs, "columns", []) or [])
        cf_cols = set(getattr(cf, "columns", []) or [])
        dates = sorted(list(set(fin_cols) | set(bs_cols) | set(cf_cols)), reverse=True)[:8]
    except Exception:
        dates = []

    saved = 0
    for d in dates:
        d_str = _safe_date_str(d)
        inc = _df_to_dict_for_date(fin, d)
        bal = _df_to_dict_for_date(bs, d)
        cas = _df_to_dict_for_date(cf, d)

        # raw
        if inc:
            if save_full_statement_record(symbol, "income", p_type, d_str, inc, scale="raw", source=source):
                saved += 1
            # thousands
            inc_k = {k: (_safe_float(v) / 1000.0) for k, v in inc.items()}
            save_full_statement_record(symbol, "income", p_type, d_str, inc_k, scale="thousands", source=source)

        if bal:
            if save_full_statement_record(symbol, "balance", p_type, d_str, bal, scale="raw", source=source):
                saved += 1
            bal_k = {k: (_safe_float(v) / 1000.0) for k, v in bal.items()}
            save_full_statement_record(symbol, "balance", p_type, d_str, bal_k, scale="thousands", source=source)

        if cas:
            if save_full_statement_record(symbol, "cashflow", p_type, d_str, cas, scale="raw", source=source):
                saved += 1
            cas_k = {k: (_safe_float(v) / 1000.0) for k, v in cas.items()}
            save_full_statement_record(symbol, "cashflow", p_type, d_str, cas_k, scale="thousands", source=source)

    return saved


def sync_full_yahoo(symbol: str, period: str = "both") -> Tuple[bool, str]:
    """Sync and store *full* statements (income/balance/cashflow) from yfinance.

    period:
      - "annual" | "quarterly" | "both"

    Saves RAW + THOUSANDS scales to financialstatements_raw.
    """
    symbol = get_ticker_symbol(symbol)
    ensure_financialstatements_raw_table()

    p = str(period or "both").strip().lower()
    if p not in ("annual", "quarterly", "both"):
        p = "both"

    try:
        t = yf.Ticker(symbol)
        saved = 0

        if p in ("annual", "both"):
            saved += _save_full_pack(symbol, t.financials, t.balance_sheet, t.cashflow, "Annual", source="yfinance")
        if p in ("quarterly", "both"):
            saved += _save_full_pack(
                symbol,
                t.quarterly_financials,
                t.quarterly_balance_sheet,
                t.quarterly_cashflow,
                "Quarterly",
                source="yfinance",
            )

        if saved <= 0:
            return False, "لم يتم حفظ أي قوائم كاملة من yfinance (قد تكون غير متاحة أو محجوبة)."
        label = "سنوي" if p == "annual" else ("ربع سنوي" if p == "quarterly" else "سنوي+ربع سنوي")
        return True, f"تم حفظ {saved} سجلات قوائم كاملة (RAW+Thousands) — {label}."
    except Exception as e:
        return False, f"فشل مزامنة القوائم الكاملة: {e}"



" | ".join(notes)


# ==============================================================
# ⚡ Yahoo Sync (used by views.py)
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
                fin = {}
            if bs is None:
                bs = {}
            if cf is None:
                cf = {}

            # yfinance objects may be DataFrames; keep same best-effort logic
            try:
                fin_empty = getattr(fin, "empty", True)
                bs_empty = getattr(bs, "empty", True)
                cf_empty = getattr(cf, "empty", True)
            except Exception:
                fin_empty, bs_empty, cf_empty = True, True, True

            if fin_empty and bs_empty and cf_empty:
                return 0

            try:
                fin_cols = set(getattr(fin, "columns", []) or [])
                bs_cols = set(getattr(bs, "columns", []) or [])
                cf_cols = set(getattr(cf, "columns", []) or [])
                dates = sorted(list(set(fin_cols) | set(bs_cols) | set(cf_cols)), reverse=True)[:6]
            except Exception:
                dates = []

            if not dates:
                return 0

            def g(df, k, d):
                try:
                    if df is None or getattr(df, "empty", True):
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
                    "total_liabilities": (
                        g(bs, "Total Liabilities Net Minority Interest", d) or g(bs, "Total Liabilities", d)
                    ),
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
# 📦 Full Statements Sync (Annual/Quarterly) — Optional
# ==============================================================
def sync_full_yahoo(symbol: str, period: str = 'all', *, include_ttm: bool = True) -> Tuple[bool, str]:
    """
    Fetch and store ALL line-items for:
      - Income statement
      - Balance sheet
      - Cashflow statement
    For Annual/Quarterly (or all) (+ optional TTM derived)
    Values are stored in *thousands* to match Yahoo UI.
    """
    from .yahoo_data import fetch_full_financial_statements_yahoo_json, diagnose_quote_summary
    from .store_full import save_full_statement_record, has_full_statement, fetch_full_statement_records

    # ----------------------------------------------------------
    # ✅ Throttle/cache (module-level, process-only)
    # - reduces repeated Yahoo hits during Streamlit reruns
    # ----------------------------------------------------------
    import time as _time

    global _FULL_YAHOO_CACHE, _FULL_YAHOO_CACHE_TS, _FULL_YAHOO_LAST_FAIL
    try:
        _FULL_YAHOO_CACHE
    except Exception:
        _FULL_YAHOO_CACHE = {}
        _FULL_YAHOO_CACHE_TS = {}
        _FULL_YAHOO_LAST_FAIL = {}

    period_norm = (period or 'all').lower()
    if period_norm in ('a','annual','y','year','yearly'):
        period_type_req = 'Annual'
    elif period_norm in ('q','quarter','quarterly'):
        period_type_req = 'Quarterly'
    else:
        period_type_req = 'All'

    cache_key = f"{symbol}::{period_type_req}"
    now = _time.time()
    ttl = 6 * 60 * 60  # 6h
    cooldown = 60      # 60s after failure

    ts = float(_FULL_YAHOO_CACHE_TS.get(cache_key, 0.0) or 0.0)
    if ts and (now - ts) < ttl:
        cached = _FULL_YAHOO_CACHE.get(cache_key) or {}
        if isinstance(cached, dict) and cached:
            data = cached
        else:
            data = {}
    else:
        data = {}

    symbol = get_ticker_symbol(symbol)

    try:
        # If we have fresh cached full bundle, skip network.
        if not data:
            # Cooldown after failures (avoid hammering Yahoo on reruns)
            last_fail = float(_FULL_YAHOO_LAST_FAIL.get(cache_key, 0.0) or 0.0)
            if last_fail and (now - last_fail) < cooldown:
                if has_full_statement(symbol):
                    return True, "⚠️ تم عرض آخر قوائم كاملة محفوظة (تجنبًا لضرب Yahoo أثناء التحديثات)."
                return False, "⚠️ تم إيقاف المحاولة مؤقتًا لتجنب 429. أعد المحاولة بعد دقيقة."

            data = fetch_full_financial_statements_yahoo_json(
                symbol,
                period_type=period_type_req,
                as_thousands=True,
                include_ttm=include_ttm,
            ) or {}

            # cache success
            if data:
                _FULL_YAHOO_CACHE[cache_key] = data
                _FULL_YAHOO_CACHE_TS[cache_key] = now

        if not data:
            diag = diagnose_quote_summary(symbol) or {}
            status = str(diag.get("status") or "").strip()
            err = str(diag.get("error") or "").strip()
            hint = str(diag.get("hint") or "").strip()
            details = ""
            if status or err:
                details = f" التفاصيل: status={status}, error={err}"
                if hint:
                    details += f" | hint={hint}"

            # mark fail time for cooldown
            _FULL_YAHOO_LAST_FAIL[cache_key] = now

            # fallback to stored full statements if exist
            if has_full_statement(symbol):
                # just confirm we can read them
                _ = fetch_full_statement_records(symbol, limit=1)
                return True, "⚠️ Yahoo غير متاح الآن. تم عرض آخر قوائم كاملة محفوظة." + details

            # fallback to summary (multi sources) so the rest of the app can still work
            ok2, msg2 = sync_auto_multi_sources(symbol, prefer="yahoo")
            if ok2:
                return True, "⚠️ لم تُجلب القوائم الكاملة من Yahoo، لكن تم تحديث القوائم الأساسية من مصادر بديلة. " + msg2 + details

            return False, "❌ لم يتم جلب أي بيانات كاملة من Yahoo." + details + "\n"

        saved = 0
        requested = (period or 'all').lower()
        allow_annual = (requested == 'all') or requested.startswith('a')
        allow_quarterly = (requested == 'all') or requested.startswith('q')
        allow_ttm = (requested == 'all') or include_ttm
        for period_type, bundle in data.items():
            if period_type_req != 'All' and period_type != period_type_req and period_type != ('TTM' if period_type_req=='Annual' else ''):
                continue
            if period_type == 'Annual' and not allow_annual:
                continue
            if period_type == 'Quarterly' and not allow_quarterly:
                continue
            if period_type == 'TTM' and not allow_ttm:
                continue
            for statement, recs in (bundle or {}).items():
                for r in recs or []:
                    d = (r or {}).get("date")
                    payload = (r or {}).get("data") or {}
                    if not d or not isinstance(payload, dict) or not payload:
                        continue
                    ok = save_full_statement_record(
                        symbol,
                        statement=statement,
                        period_type=period_type,
                        as_of=d,
                        data=payload,
                        scale="thousands",
                        source="YahooJSON",
                    )
                    if ok:
                        saved += 1

        if saved == 0:
            return False, "⚠️ تم الجلب لكن لم يتم حفظ أي سجل (تحقق من DB)."
        return True, f"✅ تم حفظ {saved} سجلات (قوائم كاملة) لـ {symbol}."

    except Exception as e:
        from osoli_logging import log_exception
        log_exception(e, "sync_full_yahoo failed")
        return False, f"❌ خطأ أثناء مزامنة القوائم الكاملة: {e}"
