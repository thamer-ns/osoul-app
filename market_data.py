# market_data.py

import re
import time
import json
from typing import List, Dict, Any, Optional

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- Unicode cleanup (RTL/LTR marks) ---------------------------------
_BIDI_STRIP_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
def _clean_symbol_text(s: str) -> str:
    """Normalize symbol text from RTL UIs / copy-paste.

    - removes invisible direction marks
    - normalizes several dot-like separators to '.'
    - strips whitespace
    """
    s = str(s or "")
    s = _BIDI_STRIP_RE.sub("", s)
    # normalize dot variants (Arabic decimal separator, fullwidth, middle-dot, etc.)
    for ch in ("٫", "·", "•", "。", "．", "٬"):
        s = s.replace(ch, ".")
    return s.strip()

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
    """توحيد الرموز لتوافق Yahoo Finance.

    يدعم أشكال إدخال شائعة من واجهات مختلفة:
    - 1150  -> 1150.SR
    - 1150.SR -> 1150.SR
    - SR.1150 / SR1150 -> 1150.SR  ✅ (كان سبب اختفاء البيانات المخزنة)
    - TASI -> ^TASI.SR
    """
    s = _clean_symbol_text(str(symbol or "")).strip().upper()
    if not s:
        return ""

    # indices
    if s in ["TASI", ".TASI", "^TASI", "^TASI.SR"]:
        return "^TASI.SR"

    # normalize common UI formats: SR.1150 / SR1150
    m = re.match(r"^SR\.?([0-9]{1,6})$", s)
    if m:
        return f"{m.group(1)}.SR"

    # plain digits
    if s.isdigit():
        return f"{s}.SR"

    # allow already-normalized
    if s.startswith("^"):
        return s

    # if ends with SR but missing dot
    if s.endswith("SR") and not s.endswith(".SR"):
        s = s[:-2] + ".SR"

    # if missing .SR (typical equities)
    if not s.endswith(".SR") and not s.startswith("^"):
        return f"{s}.SR"

    return s


def _symbol_variants(symbol: str) -> List[str]:
    raw = _clean_symbol_text(str(symbol or "")).strip().upper()
    if not raw:
        return []

    norm = get_ticker_symbol(raw)
    variants = [raw, norm]

    # strip .SR where applicable
    if norm.endswith(".SR"):
        variants.append(norm.replace(".SR", ""))
    if raw.endswith(".SR"):
        variants.append(raw.replace(".SR", ""))

    # also try SR.#### and SR#### forms (some UIs)
    m = re.match(r"^([0-9]{1,6})\.SR$", norm)
    if m:
        variants.append(f"SR.{m.group(1)}")
        variants.append(f"SR{m.group(1)}")

    out, seen = [], set()
    for x in variants:
        x = str(x or "").strip().upper()
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

    # MultiIndex fix
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

    # Tuple columns fix
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

    d = d.dropna(subset=[c for c in needed if c in d.columns], how="any")
    d = _ensure_datetime_index(d)

    # remove invalid candles
    if not d.empty and "Close" in d.columns:
        d = d[pd.to_numeric(d["Close"], errors="coerce").fillna(0) > 0]

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
    s = _clean_symbol_text(str(symbol or "")).strip().upper()
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
def fetch_price_from_yahoo(symbol: str) -> Dict[str, Any]:
    """Disabled for price retrieval.

    Policy: Yahoo is used for financial statements only.
    (Yahoo price endpoints are rate-limited and duplicate Google/other sources.)
    """
    sym = get_ticker_symbol(symbol)
    return {
        "source": "yahoo",
        "symbol": sym,
        "price": 0.0,
        "prev_close": 0.0,
        "year_high": 0.0,
        "year_low": 0.0,
        "ok": False,
        "note": "Yahoo price fetching is disabled (statements-only mode).",
    }


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
                df = df.dropna(subset=[c for c in ["Open", "High", "Low", "Close"] if c in df.columns], how="any")
                df = _ensure_datetime_index(df)
                if not df.empty and "Close" in df.columns:
                    return df
        except Exception:
            pass
        finally:
            # ✅ Gentle backoff to reduce rate-limit pressure
            time.sleep(0.25)

    return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def get_tasi_data():
    """Return (index_level, percent_change) for TASI.

    Prices source policy:
    - Use Google Finance first for TASI snapshot (TASI:TADAWUL / ^TASI.SR).
    - Then TradingView / Investing snapshots.
    - Avoid Yahoo endpoints for prices to reduce 429 and comply with statements-only mode.
    """
    # Google Finance
    snap = fetch_google_finance_snapshot("^TASI.SR")
    curr = _safe_float((snap or {}).get("price", 0.0)) if isinstance(snap, dict) else 0.0
    if curr > 0:
        # Google Finance HTML does not reliably expose previous close in a stable selector.
        return curr, 0.0

    # Fallbacks (snapshot-only)
    tv = fetch_tradingview_snapshot("^TASI.SR")
    curr2 = _safe_float((tv or {}).get("price", 0.0)) if isinstance(tv, dict) else 0.0
    if curr2 > 0:
        return curr2, 0.0

    inv = fetch_investing_snapshot("^TASI.SR")
    curr3 = _safe_float((inv or {}).get("price", 0.0)) if isinstance(inv, dict) else 0.0
    if curr3 > 0:
        return curr3, 0.0

    return 0.0, 0.0


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
    Batch snapshot fetch (NO Yahoo for prices).

    Source order:
      1) Google Finance
      2) TradingView (public snapshot)
      3) Investing (public snapshot)
      4) Argaam (best-effort HTML)
    Notes:
      - prev_close / year_high / year_low may be unavailable from non-Yahoo snapshots.
      - This function focuses on *current price* for portfolio/tiles without hitting Yahoo.
    """
    results = {}
    if not symbols_list:
        return results

    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    for raw_sym in input_symbols:
        norm = get_ticker_symbol(raw_sym) or raw_sym
        out = {
            "symbol": norm,
            "price": 0.0,
            "prev_close": 0.0,
            "year_high": 0.0,
            "year_low": 0.0,
            "source": "",
            "ok": False,
        }

        # 1) Google Finance
        try:
            g = fetch_google_finance_snapshot(norm)
            if isinstance(g, dict):
                p = _safe_float(g.get("price", 0.0))
                if _is_reasonable_price(p):
                    out.update({"price": float(p), "source": "google", "ok": True})
        except Exception:
            pass

        # 2) Investing
        if out["price"] <= 0:
            try:
                inv = fetch_investing_snapshot(norm)
                if isinstance(inv, dict):
                    p = _safe_float(inv.get("price", 0.0))
                    if _is_reasonable_price(p):
                        out.update({"price": float(p), "source": "investing", "ok": True})
            except Exception:
                pass

        # 3) TradingView
        if out["price"] <= 0:
            try:
                tv = fetch_tradingview_snapshot(norm)
                if isinstance(tv, dict):
                    p = _safe_float(tv.get("price", 0.0))
                    if _is_reasonable_price(p):
                        out.update({"price": float(p), "source": "tradingview", "ok": True})
            except Exception:
                pass

        # 4) Argaam
        if out["price"] <= 0:
            try:
                ar = fetch_price_from_argaam(norm)
                if isinstance(ar, dict):
                    p = _safe_float(ar.get("price", 0.0))
                    if _is_reasonable_price(p):
                        out.update({"price": float(p), "source": "argaam", "ok": True})
            except Exception:
                pass

        results[raw_sym] = out

    return results


def get_static_info(symbol: str) -> dict:
(symbol: str) -> Dict[str, Any]:
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
