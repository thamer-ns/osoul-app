# financial_analysis/sync.py
from typing import Tuple, List

import yfinance as yf

from market_data import get_ticker_symbol
from .store import save_financial_record
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
    return False, "لم تنجح البدائل. " + " | ".join(notes)


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
