# market_data.py
import re
import time
import json
from typing import List, Dict, Any, Optional

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ✅ Optional web deps (avoid crash in some deployments)
try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None


# ============================================================
# 🌐 HTTP Safety (تأمين الاتصال)
# ============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_SESSION = None
if requests:
    _SESSION = requests.Session()
    _SESSION.headers.update(HEADERS)


def _http_get(url: str, timeout: int = 5, retries: int = 2, sleep: float = 0.5):
    if not url or not requests or not _SESSION:
        return None

    for i in range(retries + 1):
        try:
            r = _SESSION.get(url, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r
            if r.status_code == 429:
                time.sleep(sleep * 2)
        except Exception:
            pass

        if i < retries:
            time.sleep(sleep)

    return None


# ============================================================
# 🔤 Symbol Normalization (توحيد الرموز)
# ============================================================
def get_ticker_symbol(symbol: str) -> str:
    """توحيد الرموز لتوافق Yahoo Finance"""
    s = str(symbol or "").strip().upper()
    if not s:
        return ""

    if s in ["TASI", ".TASI", "^TASI", "^TASI.SR"]:
        return "^TASI.SR"

    if s.isdigit():
        return f"{s}.SR"

    if not s.startswith("^") and not s.endswith(".SR"):
        return f"{s}.SR"

    return s


def _symbol_variants(symbol: str) -> List[str]:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return []

    norm = get_ticker_symbol(raw)
    variants = [raw, norm]

    if norm.endswith(".SR"):
        variants.append(norm.replace(".SR", ""))
    if raw.endswith(".SR"):
        variants.append(raw.replace(".SR", ""))

    out, seen = [], set()
    for x in variants:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _safe_float(val) -> float:
    try:
        if val is None:
            return 0.0
        if isinstance(val, str):
            val = (
                val.replace(",", "")
                .replace("SAR", "")
                .replace("ر.س", "")
                .strip()
            )
            if val.lower() in ("nan", "none", ""):
                return 0.0
        return float(val)
    except Exception:
        return 0.0


def _is_reasonable_price(x: float) -> bool:
    try:
        x = float(x)
        return 0.01 < x < 30000
    except Exception:
        return False


def _safe_div(a, b, default=0.0):
    try:
        a = float(a)
        b = float(b)
        if b == 0:
            return default
        return a / b
    except Exception:
        return default


# ============================================================
# 🧼 Index Cleaner (مهم جداً لمنع "الخط العمودي" في الشارت)
# ============================================================
def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()

    for c in ["date", "Date", "datetime", "Datetime", "time", "Time", "timestamp", "Timestamp"]:
        if c in d.columns:
            d[c] = pd.to_datetime(d[c], errors="coerce")
            d = d.dropna(subset=[c])
            d = d.sort_values(c)
            d = d.set_index(c)
            break

    if not isinstance(d.index, pd.DatetimeIndex):
        try:
            d.index = pd.to_datetime(d.index, errors="coerce")
        except Exception:
            pass

    d = d[~pd.isna(d.index)]
    d = d[~d.index.duplicated(keep="last")]
    try:
        d = d.sort_index()
    except Exception:
        pass

    return d


# ============================================================
# 🧱 OHLCV Normalizer (Fix MultiIndex/Tuple Columns)
# ============================================================
def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()

    if isinstance(d.columns, pd.MultiIndex):
        levels = list(range(d.columns.nlevels))
        ohlcv_keys = {"open", "high", "low", "close", "adj close", "volume", "adjclose"}

        best_level = 0
        best_hit = -1
        for lv in levels:
            vals = [str(x).strip().lower() for x in d.columns.get_level_values(lv)]
            hit = sum(1 for v in vals if v in ohlcv_keys)
            if hit > best_hit:
                best_hit = hit
                best_level = lv

        d.columns = d.columns.get_level_values(best_level)

    d.columns = [str(c[0] if isinstance(c, (tuple, list)) and len(c) else c) for c in d.columns]

    canonical = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj close": "Adj Close",
        "adjclose": "Adj Close",
        "volume": "Volume",
    }

    rename_map = {}
    for col in d.columns:
        key = str(col).strip().lower()
        if key in canonical:
            rename_map[col] = canonical[key]

    d.rename(columns=rename_map, inplace=True)

    if "Close" not in d.columns and "Adj Close" in d.columns:
        d["Close"] = d["Adj Close"]
    if "Open" not in d.columns and "Close" in d.columns:
        d["Open"] = d["Close"]

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    needed = ["Open", "High", "Low", "Close"]
    if not any(c in d.columns for c in needed):
        return pd.DataFrame()

    d = d.dropna(subset=[c for c in needed if c in d.columns], how="all")
    d = _ensure_datetime_index(d)
    return d


# ============================================================
# ⏱️ Interval Helpers (Smart defaults + Yahoo limits friendly)
# ============================================================
_INTRADAY_LIMITS = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "60d",
    "90m": "60d",
}


def _normalize_interval(interval: str) -> str:
    itv = str(interval or "").strip().lower()

    if itv in ["1h", "1hour", "hour", "ساعة"]:
        return "60m"
    if itv in ["day", "daily", "يوم", "1d"]:
        return "1d"
    if itv in ["week", "weekly", "اسبوع", "أسبوع", "1w", "1wk"]:
        return "1wk"
    if itv in ["month", "monthly", "شهر", "1mo"]:
        return "1mo"

    if itv == "1w":
        return "1wk"

    return itv or "1d"


def _default_period_for_interval(interval: str, years: int = 5) -> str:
    itv = _normalize_interval(interval)

    if itv in _INTRADAY_LIMITS:
        return _INTRADAY_LIMITS[itv]

    if years and years >= 5:
        return "5y"
    if years and years >= 2:
        return "2y"
    return "1y"


def _build_period_fallbacks(interval: str, period: str, years: int) -> List[str]:
    itv = _normalize_interval(interval)
    prd = (period or "").strip().lower()

    if not prd:
        prd = _default_period_for_interval(itv, years=years)

    if itv in _INTRADAY_LIMITS:
        lim = _INTRADAY_LIMITS.get(itv, "60d")
        tries = []
        if prd:
            tries.append(prd)
        if lim not in tries:
            tries.append(lim)
        tries += ["60d", "30d", "14d", "7d"]
        out, seen = [], set()
        for x in tries:
            if x and x not in seen:
                out.append(x)
                seen.add(x)
        return out

    tries = [prd, "5y", "2y", "1y", "6mo", "3mo", "max"]
    out, seen = [], set()
    for x in tries:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


# ============================================================
# 📈 Google Finance (Snapshot)
# ============================================================
def fetch_google_finance_snapshot(symbol: str) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}

    norm = get_ticker_symbol(sym)

    if norm.startswith("^"):
        return {"source": "google_finance", "price": 0.0, "ok": False, "note": "Index pages differ."}

    if not BeautifulSoup:
        return {"source": "google_finance", "price": 0.0, "ok": False, "note": "bs4 not installed."}

    ticker = norm.replace(".SR", "").replace("^", "")
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"

    r = _http_get(url, timeout=5, retries=1)
    if not r:
        return {}

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        price_div = soup.find("div", {"class": "YMlKec fxKbKc"})
        price = 0.0
        if price_div and price_div.text:
            txt = price_div.text.replace(",", "").replace("SAR", "").strip()
            price = _safe_float(txt)

        if _is_reasonable_price(price):
            return {"source": "google_finance", "price": price, "url": url, "ok": True}
        return {"source": "google_finance", "price": 0.0, "url": url, "ok": False}
    except Exception:
        return {}


# ============================================================
# 📊 TradingView / Investing (Placeholders)
# ============================================================
def fetch_tradingview_snapshot(symbol: str) -> Dict[str, Any]:
    return {"source": "tradingview", "ok": False, "note": "Disabled by default."}


def fetch_investing_snapshot(symbol: str) -> Dict[str, Any]:
    return {"source": "investing", "ok": False, "note": "Disabled by default."}


# ============================================================
# 🟦 Argaam (أرقام) - المصدر الاحتياطي القوي
# ============================================================
def _extract_argaam_price_from_html(html: str) -> float:
    if not html or not BeautifulSoup:
        return 0.0

    soup = BeautifulSoup(html, "html.parser")

    meta_selectors = [
        ("meta", {"property": "product:price:amount"}),
        ("meta", {"property": "og:price:amount"}),
        ("meta", {"itemprop": "price"}),
    ]
    for tag, attrs in meta_selectors:
        m = soup.find(tag, attrs=attrs)
        if m and m.get("content"):
            p = _safe_float(m.get("content"))
            if _is_reasonable_price(p):
                return p

    text = html
    json_patterns = [
        r'"lastPrice"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r'"Close"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
    ]
    for pat in json_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            p = _safe_float(m.group(1))
            if _is_reasonable_price(p):
                return p

    price_spans = soup.find_all("span", class_=re.compile("price|value|last", re.I))
    for span in price_spans:
        p = _safe_float(span.text)
        if _is_reasonable_price(p):
            return p

    return 0.0


def fetch_price_from_argaam(symbol: str) -> float:
    s = str(symbol or "").strip().upper()
    if not s:
        return 0.0

    code = s.replace(".SR", "").replace("^", "")
    if not code.isdigit():
        return 0.0

    url_candidates = [
        f"https://www.argaam.com/ar/company/stock/overview/{code}",
        f"https://www.argaam.com/en/company/stock/overview/{code}",
        f"https://www.argaam.com/ar/company/stock/quote/{code}",
    ]

    for url in url_candidates:
        r = _http_get(url, timeout=6, retries=1)
        if not r:
            continue
        p = _extract_argaam_price_from_html(r.text)
        if _is_reasonable_price(p):
            return float(p)

    return 0.0


# ============================================================
# 🟨 Yahoo Finance - المصدر الأساسي
# ============================================================
def fetch_price_from_yahoo(symbol: str) -> Dict[str, float]:
    sym = get_ticker_symbol(symbol)
    default_res = {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}

    if not sym:
        return default_res

    try:
        t = yf.Ticker(sym)
        fi = getattr(t, "fast_info", None)

        last_price = 0.0
        prev_close = 0.0
        year_high = 0.0
        year_low = 0.0

        if fi:
            last_price = _safe_float(getattr(fi, "last_price", None))
            prev_close = _safe_float(getattr(fi, "previous_close", None))
            year_high = _safe_float(getattr(fi, "year_high", None))
            year_low = _safe_float(getattr(fi, "year_low", None))

        if last_price <= 0 or prev_close <= 0:
            try:
                h = t.history(period="5d", interval="1d")
                h = _normalize_ohlcv_columns(h)
                if not h.empty and "Close" in h.columns:
                    if last_price <= 0:
                        last_price = _safe_float(h["Close"].iloc[-1])
                    if prev_close <= 0 and len(h) >= 2:
                        prev_close = _safe_float(h["Close"].iloc[-2])
            except Exception:
                pass

        return {
            "price": float(last_price) if _is_reasonable_price(last_price) else 0.0,
            "prev_close": float(prev_close) if _is_reasonable_price(prev_close) else 0.0,
            "year_high": float(year_high) if _is_reasonable_price(year_high) else 0.0,
            "year_low": float(year_low) if _is_reasonable_price(year_low) else 0.0,
        }
    except Exception:
        return default_res


# ============================================================
# 📌 TASI Data (المؤشر العام)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_tasi_data():
    try:
        tick = yf.Ticker("^TASI.SR")
        fi = getattr(tick, "fast_info", None)
        curr = _safe_float(getattr(fi, "last_price", None)) if fi else 0.0
        prev = _safe_float(getattr(fi, "previous_close", None)) if fi else 0.0

        if curr <= 0:
            hist = tick.history(period="5d", interval="1d")
            hist = _normalize_ohlcv_columns(hist)
            if not hist.empty and "Close" in hist.columns:
                curr = _safe_float(hist["Close"].iloc[-1])
                prev = _safe_float(hist["Close"].iloc[-2]) if len(hist) > 1 else curr

        if _is_reasonable_price(curr):
            chg = ((curr - prev) / prev) * 100.0 if prev > 0 else 0.0
            return float(curr), round(_safe_float(chg), 2)
    except Exception:
        pass

    return 0.0, 0.0


# ============================================================
# 📉 Chart History (للرسم البياني والذكاء الاصطناعي)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_chart_history(symbol: str, period: str = None, interval: str = "1d", years: int = 5) -> pd.DataFrame:
    sym = get_ticker_symbol(symbol)
    if not sym:
        return pd.DataFrame()

    itv = _normalize_interval(interval)
    tries = _build_period_fallbacks(itv, period=period, years=years)

    for p in tries:
        try:
            df = yf.download(
                sym,
                period=p,
                interval=itv,
                auto_adjust=False,
                progress=False,
                threads=False,
                group_by="column",
            )
            df = _normalize_ohlcv_columns(df)

            if df is not None and not df.empty:
                df = _ensure_datetime_index(df)
                if not df.empty and "Close" in df.columns:
                    return df
        except Exception:
            pass

    return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def get_tasi_history(period: str = None, interval: str = "1d") -> pd.DataFrame:
    return get_chart_history("^TASI.SR", period=period, interval=interval, years=5)


def get_relative_strength_vs_tasi(symbol: str, period: str = None, interval: str = "1d") -> Dict[str, Any]:
    sym = get_ticker_symbol(symbol)

    stock = get_chart_history(sym, period=period, interval=interval, years=5)
    tasi = get_tasi_history(period=period, interval=interval)

    if stock is None or stock.empty or "Close" not in stock.columns:
        return {"ok": False, "symbol": sym, "reason": "no_stock_history"}
    if tasi is None or tasi.empty or "Close" not in tasi.columns:
        return {"ok": False, "symbol": sym, "reason": "no_tasi_history"}

    df = pd.DataFrame(
        {
            "stock": pd.to_numeric(stock["Close"], errors="coerce"),
            "tasi": pd.to_numeric(tasi["Close"], errors="coerce"),
        }
    ).dropna()

    df = _ensure_datetime_index(df)

    if df.empty or len(df) < 30:
        return {"ok": False, "symbol": sym, "reason": "insufficient_overlap"}

    df["rs"] = df["stock"] / df["tasi"]
    df["stock_ret"] = df["stock"].pct_change()
    df["tasi_ret"] = df["tasi"].pct_change()
    df["rel_ret"] = (1 + df["stock_ret"]) / (1 + df["tasi_ret"]) - 1

    def _window_outperf(n):
        if len(df) <= n:
            return 0.0
        s = df["stock"].iloc[-1] / df["stock"].iloc[-(n + 1)] - 1
        i = df["tasi"].iloc[-1] / df["tasi"].iloc[-(n + 1)] - 1
        return float(s - i)

    out_1m = _window_outperf(21)
    out_3m = _window_outperf(63)
    out_6m = _window_outperf(126)
    out_1y = _window_outperf(252)

    rs_now = float(df["rs"].iloc[-1])
    rs_chg_3m = float(df["rs"].iloc[-1] / df["rs"].iloc[-64] - 1) if len(df) > 64 else 0.0

    label = "محايد"
    if out_3m > 0.05 and out_1m > 0:
        label = "أقوى من تاسي"
    elif out_3m < -0.05 and out_1m < 0:
        label = "أضعف من تاسي"

    return {
        "ok": True,
        "symbol": sym,
        "rs_now": rs_now,
        "rs_change_3m": rs_chg_3m,
        "outperf_1m": out_1m,
        "outperf_3m": out_3m,
        "outperf_6m": out_6m,
        "outperf_1y": out_1y,
        "label": label,
        "rs_series": df["rs"].tail(260).to_dict(),
        "asof": str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) and len(df.index) else "",
    }


@st.cache_data(ttl=120, show_spinner=False)
def fetch_batch_data(symbols_list: list):
    results = {}
    if not symbols_list:
        return results

    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    norm_map = {s: get_ticker_symbol(s) for s in input_symbols}
    clean_syms = sorted(list(set([v for v in norm_map.values() if v])))

    yahoo_data_by_norm = {}

    try:
        if len(clean_syms) == 1:
            sym = clean_syms[0]
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)
        else:
            tickers = yf.Tickers(" ".join(clean_syms))
            for sym in clean_syms:
                try:
                    sub_ticker = tickers.tickers.get(sym)
                    if not sub_ticker:
                        yahoo_data_by_norm[sym] = {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}
                        continue

                    fi = getattr(sub_ticker, "fast_info", None)
                    price = _safe_float(getattr(fi, "last_price", 0.0)) if fi else 0.0
                    prev_close = _safe_float(getattr(fi, "previous_close", 0.0)) if fi else 0.0

                    yahoo_data_by_norm[sym] = {
                        "price": float(price) if _is_reasonable_price(price) else 0.0,
                        "prev_close": float(prev_close) if _is_reasonable_price(prev_close) else 0.0,
                        "year_high": _safe_float(getattr(fi, "year_high", 0.0)) if fi else 0.0,
                        "year_low": _safe_float(getattr(fi, "year_low", 0.0)) if fi else 0.0,
                    }
                except Exception:
                    yahoo_data_by_norm[sym] = {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}
    except Exception:
        for sym in clean_syms:
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)

    for raw_sym in input_symbols:
        norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
        d = yahoo_data_by_norm.get(norm, {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0})

        price = _safe_float(d.get("price", 0.0))
        prev_close = _safe_float(d.get("prev_close", 0.0))
        year_high = _safe_float(d.get("year_high", 0.0))
        year_low = _safe_float(d.get("year_low", 0.0))
        source = "yahoo"

        if price <= 0:
            p2 = fetch_price_from_argaam(raw_sym)
            if _is_reasonable_price(p2):
                price = float(p2)
                if prev_close <= 0:
                    prev_close = float(p2)
                source = "argaam"
            else:
                source = "failed"

        res_entry = {
            "price": price,
            "prev_close": prev_close,
            "year_high": year_high,
            "year_low": year_low,
            "source": source,
        }

        results[raw_sym] = res_entry

        for v in _symbol_variants(raw_sym):
            results.setdefault(v, res_entry)

    return results


def get_static_info(symbol: str) -> Dict[str, Any]:
    sym = get_ticker_symbol(symbol) or str(symbol or "").strip().upper()
    name = sym
    sector = "Unknown"

    try:
        from data_source import get_company_details

        info = get_company_details(symbol)

        if isinstance(info, dict):
            name = info.get("name") or info.get("Name") or name
            sector = info.get("sector") or info.get("Sector") or sector
        elif isinstance(info, (list, tuple)) and len(info) >= 2:
            nm, sec = info
            if nm:
                name = nm
            if sec:
                sector = sec
    except Exception:
        pass

    return {
        "symbol": sym,
        "name": name,
        "sector": sector,
        "source": "data_source",
    }


def get_analysis_sources(symbol: str) -> Dict[str, Any]:
    sym = get_ticker_symbol(symbol)
    out = {"symbol": sym, "sources": {}}

    out["sources"]["yahoo"] = {"price_pack": fetch_price_from_yahoo(sym), "ok": True}
    out["sources"]["google_finance"] = fetch_google_finance_snapshot(sym)
    out["sources"]["tradingview"] = fetch_tradingview_snapshot(sym)
    out["sources"]["investing"] = fetch_investing_snapshot(sym)

    p_argaam = fetch_price_from_argaam(sym)
    out["sources"]["argaam"] = {"price": p_argaam, "ok": _is_reasonable_price(p_argaam)}

    out["sources"]["vs_tasi"] = get_relative_strength_vs_tasi(sym, period=None, interval="1d")

    return out