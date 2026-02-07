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
# 💹 Live Price Snapshot (Google Finance first)
# ============================================================
@st.cache_data(ttl=30, show_spinner=False)
def fetch_live_price_snapshot(symbol: str) -> Dict[str, Any]:
    """Fetch a lightweight live price snapshot.

    Priority (to reduce Yahoo requests / 429):
      1) Google Finance (TADAWUL) for stocks
      2) Argaam (أرقام) fallback
      3) Yahoo Finance (fast_info) + tiny history fallback
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"ok": False, "price": 0.0, "source": "none"}

    # 1) Google Finance (stocks only)
    gf = fetch_google_finance_snapshot(sym) or {}
    p = _safe_float(gf.get("price", 0.0))
    if gf.get("ok") and _is_reasonable_price(p):
        return {
            "ok": True,
            "price": float(p),
            "prev_close": float(_safe_float(gf.get("prev_close", 0.0))),
            "year_high": 0.0,
            "year_low": 0.0,
            "source": "google_finance",
            "url": gf.get("url", ""),
        }

    # 2) Argaam
    p2 = fetch_price_from_argaam(sym)
    if _is_reasonable_price(p2):
        return {"ok": True, "price": float(p2), "prev_close": float(p2), "year_high": 0.0, "year_low": 0.0, "source": "argaam"}

    # 3) Yahoo (fast_info)
    yd = fetch_price_from_yahoo(sym) or {}
    p3 = _safe_float(yd.get("price", 0.0))
    if _is_reasonable_price(p3):
        return {
            "ok": True,
            "price": float(p3),
            "prev_close": float(_safe_float(yd.get("prev_close", 0.0))),
            "year_high": float(_safe_float(yd.get("year_high", 0.0))),
            "year_low": float(_safe_float(yd.get("year_low", 0.0))),
            "source": "yahoo",
        }

    # tiny history (last resort)
    try:
        norm = get_ticker_symbol(sym)
        h = yf.download(norm, period="5d", interval="1d", auto_adjust=False, progress=False, threads=False, group_by="column")
        h = _normalize_ohlcv_columns(h)
        if not h.empty and "Close" in h.columns:
            last = float(_safe_float(h["Close"].iloc[-1]))
            prev = float(_safe_float(h["Close"].iloc[-2])) if len(h) >= 2 else 0.0
            if _is_reasonable_price(last):
                return {"ok": True, "price": last, "prev_close": prev, "year_high": 0.0, "year_low": 0.0, "source": "yahoo_history"}
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")

    return {"ok": False, "price": 0.0, "source": "failed"}




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
        except Exception as e:
            try:
                att['error'] = repr(e)
                _LAST_MARKET_DIAGNOSTICS['attempts'].append(att)
                _set_market_diag(ok=False, when=time.strftime('%Y-%m-%d %H:%M:%S'), symbol=sym, interval=itv, period=p, error=repr(e))
            except Exception:
                pass
            log_exception(e, "Ignored exception", level="DEBUG")
    d = d[~pd.isna(d.index)]
    d = d[~d.index.duplicated(keep="last")]
    try:
        d = d.sort_index()
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return d


# ============================================================
# 🧱 OHLCV Normalizer (Fix MultiIndex/Tuple Columns)
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
    """Normalize OHLCV columns to: Open, High, Low, Close, Adj Close, Volume.

    yfinance sometimes returns:
      - MultiIndex columns
      - tuple-like column names
      - different casing (open/high/...)
    This normalizer makes downstream AI/indicator code stable.
    """
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame()

    d = df.copy()

    # MultiIndex -> choose level that contains OHLCV keys (best hit)
    try:
        if isinstance(d.columns, pd.MultiIndex):
            ohlcv_keys = {"open", "high", "low", "close", "adj close", "adjclose", "volume"}
            best_level = 0
            best_hit = -1
            for lv in range(d.columns.nlevels):
                vals = [str(x).strip().lower() for x in d.columns.get_level_values(lv)]
                hit = sum(1 for v in vals if v in ohlcv_keys)
                if hit > best_hit:
                    best_hit = hit
                    best_level = lv
            d.columns = d.columns.get_level_values(best_level)
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")

    # Tuple/list columns -> pick first token
    try:
        d.columns = [str(c[0]) if isinstance(c, (tuple, list)) and len(c) else str(c) for c in d.columns]
    except Exception:
        d.columns = [str(c) for c in d.columns]

    canonical = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj close": "Adj Close",
        "adjclose": "Adj Close",
        "adj_close": "Adj Close",
        "volume": "Volume",
    }

    ren = {}
    for col in list(d.columns):
        key = str(col).strip().lower()
        if key in canonical:
            ren[col] = canonical[key]

    if ren:
        d = d.rename(columns=ren)

    d = _ensure_datetime_index(d)
    return d



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
        r = _http_get(url, timeout=7, retries=1)
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
            except Exception as e:
                log_exception(e, "Ignored exception", level="DEBUG")
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
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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

    # diagnostics init
    _set_market_diag(ok=None, when=time.strftime('%Y-%m-%d %H:%M:%S'), symbol=sym, interval=itv, period=period or f'{years}y', attempts=[], error=None)

    for p in tries:
        try:
            att = {'period': p, 'interval': itv, 'rows': 0, 'error': None}
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

            try:
                att['rows'] = int(len(df)) if df is not None else 0
            except Exception:
                pass

            if df is not None and not df.empty:
                df = df.dropna(subset=[c for c in ["Open", "High", "Low", "Close"] if c in df.columns], how="any")
                df = _ensure_datetime_index(df)
                if not df.empty and "Close" in df.columns:
                    try:
                        _LAST_MARKET_DIAGNOSTICS['attempts'].append(att)
                    except Exception:
                        pass
                    _set_market_diag(ok=True, when=time.strftime('%Y-%m-%d %H:%M:%S'), symbol=sym, interval=itv, period=p)
                    return df
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
        finally:
            try:
                if att not in _LAST_MARKET_DIAGNOSTICS.get('attempts', []):
                    _LAST_MARKET_DIAGNOSTICS['attempts'].append(att)
            except Exception:
                pass
            # ✅ Gentle backoff to reduce rate-limit pressure
            time.sleep(0.25)

    _set_market_diag(ok=False, when=time.strftime('%Y-%m-%d %H:%M:%S'), symbol=sym, interval=itv, period=period or f'{years}y')
    return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def get_tasi_history(period: str = None, interval: str = "1d") -> pd.DataFrame:
    return get_chart_history("^TASI.SR", period=period, interval=interval, years=5)


def get_multi_interval_history(symbol: str, intervals=("1d", "1wk"), years: int = 5) -> Dict[str, pd.DataFrame]:
    """
    ✅ إضافي (اختياري):
    يرجع باكيت بيانات لعدة فريمات (مفيد للـ AI).
    """
    out = {}
    for itv in intervals:
        out[str(itv)] = get_chart_history(symbol, period=None, interval=str(itv), years=years)
    return out


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
    """
    تحسينات:
    - يقلل الضغط على Yahoo (429) عبر استخدام Google Finance للسعر المباشر أولاً
    - يبقي نفس مخرجات الدالة كما هي (price/prev_close/year_high/year_low/source)
    - يضمن always mapping variants
    """
    results = {}
    if not symbols_list:
        return results

    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    norm_map = {s: get_ticker_symbol(s) for s in input_symbols}

    # 1) Live snapshot per symbol (Google Finance -> Argaam -> Yahoo fast_info)
    live_by_raw = {}
    need_yahoo_norm = []

    for raw_sym in input_symbols:
        try:
            snap = fetch_live_price_snapshot(raw_sym) or {}
        except Exception:
            snap = {}
        live_by_raw[raw_sym] = snap

        if not snap.get("ok"):
            norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
            if norm:
                need_yahoo_norm.append(norm)

    need_yahoo_norm = sorted(list(set(need_yahoo_norm)))

    # 2) Yahoo batch ONLY for symbols that still need it
    yahoo_data_by_norm = {}
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

    # 3) Compose final results with fallbacks
    for raw_sym in input_symbols:
        norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)

        snap = live_by_raw.get(raw_sym, {}) or {}
        yd = yahoo_data_by_norm.get(norm, {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0})

        if snap.get("ok"):
            price = _safe_float(snap.get("price", 0.0))
            prev_close = _safe_float(snap.get("prev_close", 0.0))
            year_high = _safe_float(snap.get("year_high", 0.0)) or _safe_float(yd.get("year_high", 0.0))
            year_low = _safe_float(snap.get("year_low", 0.0)) or _safe_float(yd.get("year_low", 0.0))
            source = str(snap.get("source") or "google_finance")
        else:
            price = _safe_float(yd.get("price", 0.0))
            prev_close = _safe_float(yd.get("prev_close", 0.0))
            year_high = _safe_float(yd.get("year_high", 0.0))
            year_low = _safe_float(yd.get("year_low", 0.0))
            source = "yahoo"

        # Yahoo history fallback (kept) if still missing price
        if price <= 0:
            try:
                h = yf.download(
                    norm,
                    period="5d",
                    interval="1d",
                    auto_adjust=False,
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

        # Argaam fallback if still missing
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
            "price": float(_safe_float(price)),
            "prev_close": float(_safe_float(prev_close)),
            "year_high": float(_safe_float(year_high)),
            "year_low": float(_safe_float(year_low)),
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
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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
