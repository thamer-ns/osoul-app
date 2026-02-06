from osoli_logging import log_exception
# market_data.py

import re
import time
import json
from typing import List, Dict, Any, Optional

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np


# ============================================================
# Diagnostics: market/price history fetch (yfinance)
# ============================================================
_LAST_MARKET_DIAGNOSTICS: Dict[str, Any] = {
    "ok": None, "when": None, "symbol": None, "interval": None, "period": None,
    "attempts": [], "error": None,
}

def _set_market_diag(**kw):
    try:
        _LAST_MARKET_DIAGNOSTICS.update(kw)
    except Exception:
        pass

def get_last_market_diagnostics() -> Dict[str, Any]:
    """Return last diagnostics for price-history fetching."""
    return dict(_LAST_MARKET_DIAGNOSTICS)

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


def _http_get(url: str, timeout: int = 6, retries: int = 2, sleep: float = 0.6):
    """
    robust http get:
    - exponential backoff on failures/429
    """
    if not url or not requests or not _SESSION:
        return None

    for i in range(retries + 1):
        try:
            r = _SESSION.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and r.text:
                return r

            # rate limit
            if r.status_code == 429:
                time.sleep(sleep * (2 ** i))
            else:
                time.sleep(sleep * (1 + i * 0.3))
        except Exception:
            time.sleep(sleep * (1 + i * 0.5))

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


# ============================================================
# 💹 Live Price (Google Finance first)
# ============================================================
@st.cache_data(ttl=30, show_spinner=False)
def fetch_live_price_snapshot(symbol: str) -> Dict[str, Any]:
    """Fetch a lightweight live price snapshot.

    Priority (to reduce Yahoo requests):
      1) Google Finance (TADAWUL)
      2) Argaam (أرقام) fallback
      3) Yahoo fast_info / history fallback
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"ok": False, "price": 0.0, "source": "none"}

    # 1) Google Finance
    gf = fetch_google_finance_snapshot(sym) or {}
    price = _safe_float(gf.get("price", 0.0))
    if gf.get("ok") and _is_reasonable_price(price):
        return {
            "ok": True,
            "price": float(price),
            "prev_close": float(_safe_float(gf.get("prev_close", 0.0))) if _is_reasonable_price(_safe_float(gf.get("prev_close", 0.0))) else 0.0,
            "year_high": 0.0,
            "year_low": 0.0,
            "source": "google_finance",
            "url": gf.get("url", ""),
        }

    # 2) Argaam (price only)
    p2 = fetch_price_from_argaam(sym)
    if _is_reasonable_price(p2):
        return {
            "ok": True,
            "price": float(p2),
            "prev_close": float(p2),
            "year_high": 0.0,
            "year_low": 0.0,
            "source": "argaam",
        }

    # 3) Yahoo (best-effort)
    yd = fetch_price_from_yahoo(sym) or {}
    price = _safe_float(yd.get("price", 0.0))
    if _is_reasonable_price(price):
        return {
            "ok": True,
            "price": float(price),
            "prev_close": float(_safe_float(yd.get("prev_close", 0.0))),
            "year_high": float(_safe_float(yd.get("year_high", 0.0))),
            "year_low": float(_safe_float(yd.get("year_low", 0.0))),
            "source": "yahoo",
        }

    # Yahoo history as last attempt (kept very light)
    try:
        norm = get_ticker_symbol(sym)
        h = yf.download(
            norm,
            period="5d",
            interval="1d",
            progress=False,
            threads=False,
            group_by="column",
        )
        h = _normalize_ohlcv_columns(h)
        if not h.empty and "Close" in h.columns:
            price = float(_safe_float(h["Close"].iloc[-1]))
            prev = float(_safe_float(h["Close"].iloc[-2])) if len(h) >= 2 else 0.0
            if _is_reasonable_price(price):
                return {"ok": True, "price": price, "prev_close": prev, "source": "yahoo_history"}
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")

    return {"ok": False, "price": 0.0, "source": "failed"}


# ============================================================
# 🧼 Index Cleaner (مهم 
# ============================================================
def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    try:
        if df is None or df.empty:
            return df
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[~df.index.isna()]
        return df
    except Exception:
        return df


def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Handle yfinance multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        # Often: (Price, 'Open'), etc. We'll flatten.
        df.columns = [c[-1] if isinstance(c, tuple) else c for c in df.columns]

    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj close": "Adj Close",
        "volume": "Volume",
    }
    new_cols = {}
    for c in df.columns:
        lc = str(c).strip().lower()
        if lc in rename_map:
            new_cols[c] = rename_map[lc]
        else:
            # keep original for unknown
            new_cols[c] = c

    df.rename(columns=new_cols, inplace=True)
    df = _ensure_datetime_index(df)
    return df


def _normalize_interval(interval: str) -> str:
    it = str(interval or "1d").strip().lower()
    ok = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}
    if it == "1h":
        it = "60m"
    if it in ok:
        return it
    return "1d"


def _default_period_for_interval(interval: str) -> str:
    it = _normalize_interval(interval)
    # Keep periods small for intraday
    if it in {"1m", "2m", "5m"}:
        return "5d"
    if it in {"15m", "30m"}:
        return "1mo"
    if it in {"60m", "90m"}:
        return "3mo"
    if it in {"1wk"}:
        return "2y"
    if it in {"1mo", "3mo"}:
        return "10y"
    return "2y"


def _build_period_fallbacks(period: str) -> List[str]:
    p = str(period or "").strip()
    if not p:
        return ["1y", "2y", "5y", "10y"]
    fallbacks = [p]
    # heuristic fallback chain
    chain = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"]
    if p not in chain:
        return fallbacks + ["1y", "2y", "5y"]
    i = chain.index(p)
    return fallbacks + chain[i+1:]


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

    r = _http_get(url, timeout=6, retries=1)
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
            return _safe_float(m["content"])

    # fallback: try common spans
    try:
        # Sometimes price appears in elements with class 'price' etc.
        for cls in ["price", "LastPrice", "stockPrice", "market-price"]:
            el = soup.find(class_=cls)
            if el and el.text:
                p = _safe_float(el.text)
                if _is_reasonable_price(p):
                    return p
    except Exception:
        pass

    return 0.0


def fetch_price_from_argaam(symbol: str) -> float:
    """
    Fetch current price from Argaam (أرقام) website (best-effort).
    """
    if not requests or not BeautifulSoup:
        return 0.0

    sym = str(symbol or "").strip().upper()
    if not sym:
        return 0.0

    ticker = get_ticker_symbol(sym).replace(".SR", "").replace("^", "")

    url = f"https://www.argaam.com/ar/company/profile/stock/{ticker}"

    r = _http_get(url, timeout=6, retries=1)
    if not r:
        return 0.0

    try:
        p = _extract_argaam_price_from_html(r.text)
        return float(p) if _is_reasonable_price(p) else 0.0
    except Exception:
        return 0.0


def fetch_price_from_yahoo(symbol: str) -> Dict[str, float]:
    sym = get_ticker_symbol(symbol)
    default_res = {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}

    try:
        t = yf.Ticker(sym)
        fi = getattr(t, "fast_info", None)
        price = _safe_float(getattr(fi, "last_price", 0.0)) if fi else 0.0
        prev_close = _safe_float(getattr(fi, "previous_close", 0.0)) if fi else 0.0

        # Reasonable fallbacks
        if not _is_reasonable_price(price):
            price = 0.0
        if not _is_reasonable_price(prev_close):
            prev_close = 0.0

        year_high = _safe_float(getattr(fi, "year_high", 0.0)) if fi else 0.0
        year_low = _safe_float(getattr(fi, "year_low", 0.0)) if fi else 0.0

        return {
            "price": float(price),
            "prev_close": float(prev_close),
            "year_high": float(year_high),
            "year_low": float(year_low),
        }
    except Exception:
        return default_res


def get_tasi_data():
    """
    Return a stable dict for TASI snapshot.
    """
    return fetch_price_from_yahoo("^TASI.SR")


def get_chart_history(symbol: str, interval: str = "1d", period: Optional[str] = None) -> pd.DataFrame:
    """
    Robust price history fetch using yfinance (cached).
    """
    symbol = get_ticker_symbol(symbol)
    interval = _normalize_interval(interval)
    period = str(period).strip() if period else _default_period_for_interval(interval)

    # diagnostics
    attempts = []
    err = None

    try:
        for p in _build_period_fallbacks(period):
            try:
                attempts.append({"period": p, "interval": interval})
                df = yf.download(symbol, period=p, interval=interval, progress=False, threads=False, group_by="column")
                df = _normalize_ohlcv_columns(df)
                if df is not None and not df.empty:
                    _set_market_diag(ok=True, when=time.time(), symbol=symbol, interval=interval, period=p, attempts=attempts, error=None)
                    return df
            except Exception as e:
                err = str(e)
                log_exception(e, "Ignored exception", level="DEBUG")
                continue
    except Exception as e:
        err = str(e)
        log_exception(e, "Ignored exception", level="DEBUG")

    _set_market_diag(ok=False, when=time.time(), symbol=symbol, interval=interval, period=period, attempts=attempts, error=err)
    return pd.DataFrame()


def get_tasi_history(interval: str = "1d", period: Optional[str] = None) -> pd.DataFrame:
    return get_chart_history("^TASI.SR", interval=interval, period=period)


def get_multi_interval_history(symbol: str, intervals: List[str] = None) -> Dict[str, pd.DataFrame]:
    intervals = intervals or ["1d", "1wk", "1mo"]
    out = {}
    for it in intervals:
        out[it] = get_chart_history(symbol, interval=it)
    return out


def get_relative_strength_vs_tasi(symbol: str, period: str = "6mo") -> float:
    """
    Compute relative strength: (symbol return - TASI return) over period.
    """
    try:
        s = get_ticker_symbol(symbol)
        df_s = yf.download(s, period=period, interval="1d", progress=False, threads=False)
        df_i = yf.download("^TASI.SR", period=period, interval="1d", progress=False, threads=False)

        df_s = _normalize_ohlcv_columns(df_s)
        df_i = _normalize_ohlcv_columns(df_i)

        if df_s.empty or df_i.empty:
            return 0.0

        rs = _window_outperf(df_s["Close"], df_i["Close"])
        return float(rs)
    except Exception:
        return 0.0


def _window_outperf(s_close: pd.Series, i_close: pd.Series) -> float:
    s_close = pd.to_numeric(s_close, errors="coerce").dropna()
    i_close = pd.to_numeric(i_close, errors="coerce").dropna()

    if len(s_close) < 2 or len(i_close) < 2:
        return 0.0

    s_ret = (s_close.iloc[-1] / s_close.iloc[0]) - 1.0
    i_ret = (i_close.iloc[-1] / i_close.iloc[0]) - 1.0
    return float(s_ret - i_ret)


@st.cache_data(ttl=120, show_spinner=False)
def fetch_batch_data(symbols_list: list):
    """
    تحسينات:
    - يقلل الضغط على yf.Tickers
    - يضمن always mapping variants
    """
    results = {}
    if not symbols_list:
        return results

    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    norm_map = {s: get_ticker_symbol(s) for s in input_symbols}
    clean_syms = sorted(list(set([v for v in norm_map.values() if v])))

    # ----------------------------------------------------------------
    # Live price snapshots (Google Finance first) to reduce Yahoo usage
    # ----------------------------------------------------------------
    yahoo_data_by_norm = {}
    google_data_by_raw = {}

    # 1) Try Google Finance per symbol (cached, very light)
    for raw_sym in input_symbols:
        try:
            snap = fetch_live_price_snapshot(raw_sym) or {}
            google_data_by_raw[raw_sym] = snap
        except Exception:
            google_data_by_raw[raw_sym] = {"ok": False}

    # 2) Batch Yahoo only for symbols that still need it
    need_yahoo_norm = []
    for raw_sym in input_symbols:
        snap = google_data_by_raw.get(raw_sym, {}) or {}
        if not snap.get("ok"):
            norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
            if norm:
                need_yahoo_norm.append(norm)

    need_yahoo_norm = sorted(list(set(need_yahoo_norm)))

    # ✅ best-effort Yahoo batch (ONLY if needed)
    try:
        if len(need_yahoo_norm) == 1:
            sym = need_yahoo_norm[0]
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)
        elif len(need_yahoo_norm) > 1:
            tickers = yf.Tickers(" ".join(need_yahoo_norm))
            for sym in need_yahoo_norm:
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
        for sym in need_yahoo_norm:
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)

    for raw_sym in input_symbols:
        norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
        snap = google_data_by_raw.get(raw_sym, {}) or {}
        d = yahoo_data_by_norm.get(norm, {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0})

        price = _safe_float(snap.get("price", 0.0)) if snap.get("ok") else _safe_float(d.get("price", 0.0))
        prev_close = _safe_float(snap.get("prev_close", 0.0)) if snap.get("ok") else _safe_float(d.get("prev_close", 0.0))
        year_high = _safe_float(d.get("year_high", 0.0))
        year_low = _safe_float(d.get("year_low", 0.0))
        source = snap.get("source", "yahoo") if snap.get("ok") else "yahoo"

        # ✅ Yahoo history fallback before Argaam
        if price <= 0:
            try:
                h = yf.download(
                    norm,
                    period="5d",
                    interval="1d",
                    progress=False,
                    threads=False,
                    group_by="column",
                )
                h = _normalize_ohlcv_columns(h)
                if not h.empty and "Close" in h.columns:
                    price = float(_safe_float(h["Close"].iloc[-1]))
                    if prev_close <= 0 and len(h) >= 2:
                        prev_close = float(_safe_float(h["Close"].iloc[-2]))
                    source = "yahoo_history"
            except Exception as e:
                log_exception(e, "Ignored exception", level="DEBUG")
        # ✅ Argaam fallback
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

        # variants mapping
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
    }


def get_analysis_sources() -> Dict[str, str]:
    return {
        "price_live_primary": "Google Finance (TADAWUL)",
        "price_live_fallback_1": "Argaam (أرقام)",
        "price_live_fallback_2": "Yahoo Finance (fast_info/history)",
        "financials_primary": "Yahoo Finance",
        "financials_fallbacks": "Argaam / Google Finance (via parsers/sync)",
        "charts_primary": "Yahoo Finance (history)",
    }
