#market_data.py
import re
import time
import json
import requests
from bs4 import BeautifulSoup

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np


# ============================================================
# 🌐 HTTP Safety
# ============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Session ثابت (أخف + أسرع)
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def _http_get(url: str, timeout: int = 5, retries: int = 1, sleep: float = 0.2):
    """
    GET آمن: retry بسيط + timeout.
    يرجع response أو None.
    """
    if not url:
        return None
    for i in range(retries + 1):
        try:
            r = _SESSION.get(url, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r
        except Exception:
            pass
        if i < retries:
            time.sleep(sleep)
    return None


# ============================================================
# 🔤 Symbol Normalization
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
    if not s.endswith(".SR") and not s.startswith("^"):
        return f"{s}.SR"
    return s


def _symbol_variants(symbol: str) -> list[str]:
    """
    مفاتيح محتملة لنفس الرمز لتجنب mismatch بين أجزاء النظام.
    """
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
        return float(val)
    except Exception:
        return 0.0


def _is_reasonable_price(x: float) -> bool:
    """
    فلتر معقولية: يمنع التقاط أرقام عشوائية من scraping.
    (تقدر توسع النطاق حسب احتياجك)
    """
    try:
        x = float(x)
        # سعر سهم/مؤشر منطقي
        return 0.01 < x < 20000
    except Exception:
        return False


# ============================================================
# 🧱 OHLCV Normalizer (Fix MultiIndex/Tuple Columns)
# ============================================================
def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    ✅ يعالج:
    - MultiIndex columns من yfinance
    - tuple/list column names
    - توحيد أسماء الأعمدة إلى: Open/High/Low/Close/Adj Close/Volume
    - تحويلها لأرقام وتصفية NaN
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # MultiIndex -> first level
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # stringify
    df.columns = [str(c[0] if isinstance(c, (tuple, list)) and len(c) else c) for c in df.columns]

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
    for col in df.columns:
        key = str(col).strip().lower()
        # لا تستخدم title() هنا — نثبت الأسماء
        rename_map[col] = canonical.get(key, col)

    df.rename(columns=rename_map, inplace=True)

    # fallback: Close من Adj Close
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df["Close"] = df["Adj Close"]

    # fallback: Open من Close
    if "Open" not in df.columns and "Close" in df.columns:
        df["Open"] = df["Close"]

    # ensure numeric
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # drop invalid
    needed = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in needed):
        return pd.DataFrame()

    df = df.dropna(subset=needed)

    # sort index
    try:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()
    except Exception:
        pass

    return df


# ============================================================
# 📈 Google Finance (analysis snapshot only)
# ============================================================
def fetch_google_finance_snapshot(symbol: str) -> dict:
    """
    مصدر مساعد للتحليل (ليس لتحديث الأسعار حسب طلبك).
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}

    ticker = sym.replace(".SR", "").replace("^", "")
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
            return {"source": "google_finance", "price": price, "url": url}
        return {"source": "google_finance", "price": 0.0, "url": url}
    except Exception:
        return {}


# ============================================================
# 📊 TradingView / Investing (analysis helpers - safe placeholders)
# ============================================================
def fetch_tradingview_snapshot(symbol: str) -> dict:
    """
    Helper للتحليل فقط — افتراضيًا مغلق لتجنب scraping غير مستقر.
    """
    return {"source": "tradingview", "ok": False, "note": "Disabled by default (stability-first)."}


def fetch_investing_snapshot(symbol: str) -> dict:
    """
    Helper للتحليل فقط — افتراضيًا مغلق لتجنب scraping غير مستقر.
    """
    return {"source": "investing", "ok": False, "note": "Disabled by default (stability-first)."}


# ============================================================
# 🟦 Argaam (أرقام) - PRICE FALLBACK for updates (as requested)
# ============================================================
def _extract_argaam_price_from_html(html: str) -> float:
    """
    محاولة دقيقة لاستخراج السعر من HTML:
    - meta tags
    - json snippets
    - final fallback محدود + تحقق معقولية
    """
    if not html:
        return 0.0

    soup = BeautifulSoup(html, "html.parser")

    # 1) Meta price candidates (أفضل من regex العام)
    meta_selectors = [
        ('meta', {"property": "product:price:amount"}),
        ('meta', {"property": "og:price:amount"}),
        ('meta', {"itemprop": "price"}),
    ]
    for tag, attrs in meta_selectors:
        m = soup.find(tag, attrs=attrs)
        if m and m.get("content"):
            p = _safe_float(m.get("content"))
            if _is_reasonable_price(p):
                return p

    # 2) JSON-like patterns داخل الصفحة
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

    # 3) DOM-based heuristic (أقل دقة، لكن أفضل من أي رقم)
    # نبحث عن SAR/ريال قريب من رقم
    raw_text = soup.get_text(" ", strip=True)
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:SAR|ريال)', raw_text, flags=re.IGNORECASE)
    if m:
        p = _safe_float(m.group(1))
        if _is_reasonable_price(p):
            return p

    return 0.0


def fetch_price_from_argaam(symbol: str) -> float:
    """
    ✅ مصدر احتياطي لتحديث الأسعار: أرقام (Argaam)
    ملاحظة: scraping قد يتغير — هنا أفضل محاولة + فلتر معقولية.
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return 0.0

    code = s.replace(".SR", "").replace("^", "")
    if not code.isdigit():
        return 0.0

    url_candidates = [
        f"https://www.argaam.com/en/company/stock/overview/{code}",
        f"https://www.argaam.com/ar/company/stock/overview/{code}",
        f"https://www.argaam.com/en/company/stock/quote/{code}",
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
# 🟨 Yahoo - PRICE (primary for updates)
# ============================================================
def fetch_price_from_yahoo(symbol: str) -> dict:
    """
    يرجع: price, prev_close, year_high, year_low
    """
    sym = get_ticker_symbol(symbol)
    if not sym:
        return {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}

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

        # fallback لو fast_info رجّع صفر
        if last_price <= 0 or prev_close <= 0:
            try:
                h = t.history(period="10d", interval="1d")
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
        return {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}


# ============================================================
# 📌 TASI
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_tasi_data():
    """جلب بيانات المؤشر العام (كاش 5 دقائق)"""
    try:
        tick = yf.Ticker("^TASI.SR")
        fi = tick.fast_info
        curr = _safe_float(getattr(fi, "last_price", None))
        prev = _safe_float(getattr(fi, "previous_close", None))
        if _is_reasonable_price(curr) and _is_reasonable_price(prev) and prev > 0:
            chg = ((curr - prev) / prev) * 100.0
            return curr, round(_safe_float(chg), 2)
    except Exception:
        pass

    # fallback (للداشبورد/التحليل فقط)
    snap = fetch_google_finance_snapshot(".TASI")
    p = _safe_float(snap.get("price", 0.0))
    return (p if _is_reasonable_price(p) else 0.0), 0.0


# ============================================================
# 📉 Chart History (Yahoo primary)  -- STABLE
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_chart_history(symbol: str, period: str = "2y", interval: str = "1d"):
    """
    يستخدمه charts.py و AI Engine.
    ✅ مطبع الأعمدة ويمنع مشاكل MultiIndex/tuple/non-string.
    """
    sym = get_ticker_symbol(symbol)
    if not sym:
        return pd.DataFrame()

    try:
        df = yf.download(
            sym,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,  # يقلل مشاكل الأعمدة أحياناً
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = _normalize_ohlcv_columns(df)
    return df


# ============================================================
# 💹 Batch Prices (Updates) = Yahoo + Argaam ONLY
# ============================================================
@st.cache_data(ttl=120, show_spinner=False)
def fetch_batch_data(symbols_list: list):
    """
    ✅ تحديث الأسعار للمحفظة/القوائم:
    - مصدر أساسي: Yahoo (yfinance)
    - مصدر احتياطي: Argaam (أرقام) فقط
    """
    results = {}
    if not symbols_list:
        return results

    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    norm_map = {s: get_ticker_symbol(s) for s in input_symbols}

    clean_syms = sorted(list(set([v for v in norm_map.values() if v])))

    yahoo_data_by_norm = {}

    # Yahoo batch
    try:
        if len(clean_syms) == 1:
            sym = clean_syms[0]
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)
        else:
            tickers = yf.Tickers(" ".join(clean_syms))
            for sym in clean_syms:
                try:
                    fi = tickers.tickers[sym].fast_info
                    yahoo_data_by_norm[sym] = {
                        "price": _safe_float(getattr(fi, "last_price", None)),
                        "prev_close": _safe_float(getattr(fi, "previous_close", None)),
                        "year_high": _safe_float(getattr(fi, "year_high", None)),
                        "year_low": _safe_float(getattr(fi, "year_low", None)),
                    }
                except Exception:
                    yahoo_data_by_norm[sym] = {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}
    except Exception:
        # fallback فردي
        for sym in clean_syms:
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)

    # Build results keyed by ORIGINAL INPUT SYMBOL
    for raw_sym in input_symbols:
        norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
        d = yahoo_data_by_norm.get(norm, {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0})

        price = _safe_float(d.get("price", 0.0))
        prev_close = _safe_float(d.get("prev_close", 0.0))
        year_high = _safe_float(d.get("year_high", 0.0))
        year_low = _safe_float(d.get("year_low", 0.0))

        # sanity
        if not _is_reasonable_price(price):
            price = 0.0
        if not _is_reasonable_price(prev_close):
            prev_close = 0.0

        # Argaam fallback ONLY
        source = "yahoo" if price > 0 else "none"
        if price <= 0:
            p2 = fetch_price_from_argaam(raw_sym)
            if _is_reasonable_price(p2):
                price = float(p2)
                if prev_close <= 0:
                    prev_close = float(p2)
                source = "argaam"

        results[raw_sym] = {
            "price": price,
            "prev_close": prev_close,
            "year_high": year_high if _is_reasonable_price(year_high) else 0.0,
            "year_low": year_low if _is_reasonable_price(year_low) else 0.0,
            "source": source,
        }

        # Store under variants too (prevents mismatches)
        for v in _symbol_variants(raw_sym):
            results.setdefault(v, results[raw_sym])

    return results


# ============================================================
# 🧾 Static Info (Stable dict for AI Engine)
# ============================================================
def get_static_info(symbol: str) -> dict:
    """
    ✅ يرجع dict (symbol/name/sector) بدون كسر لو data_source غير متوفر.
    """
    sym = get_ticker_symbol(symbol) or str(symbol or "").strip().upper()
    name = sym
    sector = None

    try:
        from data_source import get_company_details
        # يدعم: (name, sector) أو dict
        info = get_company_details(symbol)

        if isinstance(info, dict):
            name = info.get("name") or info.get("Name") or name
            sector = info.get("sector") or info.get("Sector") or sector
        else:
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


# ============================================================
# 🔎 Analysis Data Sources Registry (Optional)
# ============================================================
def get_analysis_sources(symbol: str) -> dict:
    """
    حسب طلبك: مصادر التحليل/الذكاء:
    Yahoo / Google Finance / TradingView / Argaam / Investing
    (بدون ما يعتمد عليها تحديث الأسعار)
    """
    sym = get_ticker_symbol(symbol)
    out = {"symbol": sym, "sources": {}}

    out["sources"]["yahoo"] = {"price_pack": fetch_price_from_yahoo(sym), "ok": True}
    out["sources"]["google_finance"] = fetch_google_finance_snapshot(sym)
    out["sources"]["tradingview"] = fetch_tradingview_snapshot(sym)
    out["sources"]["investing"] = fetch_investing_snapshot(sym)
    out["sources"]["argaam"] = {"price": fetch_price_from_argaam(sym), "ok": True}

    return out