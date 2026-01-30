import re
import time
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


# ============================================================
# 🔤 Symbol Normalization
# ============================================================
def get_ticker_symbol(symbol: str) -> str:
    """توحيد الرموز لتوافق Yahoo Finance"""
    s = str(symbol or "").strip().upper()
    if not s:
        return ""
    # TASI
    if s in ["TASI", ".TASI", "^TASI", "^TASI.SR"]:
        return "^TASI.SR"
    # digits -> Saudi
    if s.isdigit():
        return f"{s}.SR"
    # if no suffix and not index
    if not s.endswith(".SR") and not s.startswith("^"):
        return f"{s}.SR"
    return s


def _symbol_variants(symbol: str) -> list[str]:
    """
    يرجّع قائمة مفاتيح محتملة لنفس الرمز لتجنب عدم التطابق بين أجزاء النظام.
    مثال: "2270" -> ["2270", "2270.SR"]
    مثال: "2270.SR" -> ["2270.SR", "2270"]
    """
    raw = str(symbol or "").strip().upper()
    if not raw:
        return []

    norm = get_ticker_symbol(raw)

    variants = []
    variants.append(raw)
    variants.append(norm)

    # remove .SR variant
    if norm.endswith(".SR"):
        variants.append(norm.replace(".SR", ""))
    if raw.endswith(".SR"):
        variants.append(raw.replace(".SR", ""))

    # unique while keeping order
    out = []
    seen = set()
    for x in variants:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _safe_float(val) -> float:
    try:
        if val is None:
            return 0.0
        # بعض القيم تجي np types
        return float(val)
    except Exception:
        return 0.0


# ============================================================
# 🧱 OHLCV Normalizer (Fix MultiIndex/Tuple Columns)
# ============================================================
def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    ✅ يعالج:
    - MultiIndex columns من yfinance
    - tuple/list column names
    - توحيد أسماء الأعمدة إلى: Open/High/Low/Close/Adj Close/Volume
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # MultiIndex -> خذ أول مستوى
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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
        base = col[0] if isinstance(col, (tuple, list)) and len(col) else col
        s = str(base).strip()
        key = s.lower()
        rename_map[col] = canonical.get(key, s.title())

    df.rename(columns=rename_map, inplace=True)

    # ضمان وجود الأعمدة الأساسية (لو ناقص Open مثلاً)
    if "Open" not in df.columns and "Close" in df.columns:
        df["Open"] = df["Close"]

    return df


# ============================================================
# 📈 Google Finance (for analysis snapshot - NOT used for price update batch)
# ============================================================
def fetch_google_finance_snapshot(symbol: str) -> dict:
    """
    مصدر مساعد للتحليل (وليس لتحديث الأسعار حسب طلبك).
    يجلب السعر فقط بشكل خفيف من Google Finance.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}

    # Google غالباً يحتاج TADAWUL: 2270:TADAWUL
    ticker = sym.replace(".SR", "").replace("^", "")
    url = f"https://www.google.com/finance/quote/{ticker}:TADAWUL"

    try:
        r = requests.get(url, headers=HEADERS, timeout=4)
        if r.status_code != 200:
            return {}

        soup = BeautifulSoup(r.text, "html.parser")
        price_div = soup.find("div", {"class": "YMlKec fxKbKc"})
        price = _safe_float(
            (price_div.text or "")
            .replace(",", "")
            .replace("SAR", "")
            .strip()
        ) if price_div else 0.0

        return {"source": "google_finance", "price": price, "url": url}
    except Exception:
        return {}


# ============================================================
# 📊 TradingView / Investing (analysis helpers - best effort, may fail safely)
# ============================================================
def fetch_tradingview_snapshot(symbol: str) -> dict:
    """
    Helper للتحليل فقط.
    TradingView غالباً يحتاج endpoints خاصة وقد تتغير؛ هذه دالة best-effort.
    """
    # نتركها كـ placeholder آمن بدون scraping عميق لتفادي الأعطال
    # تقدر لاحقاً تربطها بـ paid/official APIs إذا رغبت.
    return {"source": "tradingview", "ok": False, "note": "Not enabled by default"}


def fetch_investing_snapshot(symbol: str) -> dict:
    """
    Helper للتحليل فقط.
    Investing.com يتغير كثير؛ هنا placeholder آمن.
    """
    return {"source": "investing", "ok": False, "note": "Not enabled by default"}


# ============================================================
# 🟦 Argaam (أرقام) - PRICE FALLBACK for updates (as requested)
# ============================================================
def fetch_price_from_argaam(symbol: str) -> float:
    """
    ✅ مصدر احتياطي لتحديث الأسعار: أرقام (Argaam)
    ملاحظة: صفحات أرقام قد تتغير. هذه best-effort scraping.
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return 0.0

    code = s.replace(".SR", "").replace("^", "")
    if not code.isdigit():
        # Argaam عادة أسهل مع أرقام الشركات
        return 0.0

    # محاولات روابط محتملة (قد تختلف حسب اللغة/المسار)
    url_candidates = [
        f"https://www.argaam.com/en/company/stock/overview/{code}",
        f"https://www.argaam.com/ar/company/stock/overview/{code}",
        f"https://www.argaam.com/en/company/stock/quote/{code}",
        f"https://www.argaam.com/ar/company/stock/quote/{code}",
    ]

    price = 0.0
    for url in url_candidates:
        try:
            r = requests.get(url, headers=HEADERS, timeout=4)
            if r.status_code != 200:
                continue

            html = r.text

            # محاولة regex: أي رقم قريب من "SAR" أو "ريال"
            m = re.search(r'(\d+(?:\.\d+)?)\s*(?:SAR|ريال)', html, flags=re.IGNORECASE)
            if m:
                price = _safe_float(m.group(1))
                if price > 0:
                    return price

            # محاولة parsing عامة: ابحث عن أرقام أسعار معقولة
            soup = BeautifulSoup(html, "html.parser")
            txt = soup.get_text(" ", strip=True)
            m2 = re.search(r'\b(\d{1,4}(?:\.\d{1,4})?)\b', txt)
            if m2:
                guess = _safe_float(m2.group(1))
                if 0 < guess < 10000:
                    price = guess
                    # لا نرجع مباشرة إلا إذا ما عندنا أفضل
        except Exception:
            continue

    return _safe_float(price)


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

        if fi:
            last_price = _safe_float(getattr(fi, "last_price", None))
            prev_close = _safe_float(getattr(fi, "previous_close", None))
            year_high = _safe_float(getattr(fi, "year_high", None))
            year_low = _safe_float(getattr(fi, "year_low", None))

            # fallback لو prev_close صفر
            if last_price > 0 and prev_close <= 0:
                try:
                    h = t.history(period="5d", interval="1d")
                    h = _normalize_ohlcv_columns(h)
                    if not h.empty and "Close" in h.columns and len(h) >= 2:
                        prev_close = _safe_float(h["Close"].iloc[-2])
                except Exception:
                    pass

            return {
                "price": last_price,
                "prev_close": prev_close,
                "year_high": year_high,
                "year_low": year_low,
            }
    except Exception:
        pass

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
        if curr > 0 and prev > 0:
            chg = ((curr - prev) / prev) * 100.0
            return curr, round(_safe_float(chg), 2)
    except Exception:
        pass

    # fallback (للداشبورد/التحليل فقط)
    snap = fetch_google_finance_snapshot(".TASI")
    return _safe_float(snap.get("price", 0.0)), 0.0


# ============================================================
# 📉 Chart History (Yahoo primary)  -- FIXED
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_chart_history(symbol: str, period: str = "2y", interval: str = "1d"):
    """
    يستخدمه charts.py و AI Engine.
    ✅ تم إصلاح مشكلة MultiIndex/tuple في الأعمدة.
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
            threads=False,  # يقلل مشاكل MultiIndex أحياناً
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = _normalize_ohlcv_columns(df)

    # تأكد من الترتيب
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    return df


# ============================================================
# 💹 Batch Prices (Updates) = Yahoo + Argaam ONLY (as requested)
# ============================================================
@st.cache_data(ttl=120, show_spinner=False)
def fetch_batch_data(symbols_list: list):
    """
    ✅ تحديث الأسعار للمحفظة/الصفحات:
    - مصدر أساسي: Yahoo (yfinance)
    - مصدر احتياطي: Argaam (أرقام) فقط
    """
    results = {}
    if not symbols_list:
        return results

    # نجهز mapping: كل رمز مدخل -> Yahoo normalized
    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    norm_map = {s: get_ticker_symbol(s) for s in input_symbols}

    # 1) Yahoo batch
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
        # fallback: لو فشل batch تماماً، نحاول فردي
        for sym in clean_syms:
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)

    # 2) Build results keyed by ORIGINAL INPUT SYMBOL (مهم لتوافق views.py)
    for raw_sym in input_symbols:
        norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
        d = yahoo_data_by_norm.get(norm, {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0})

        price = _safe_float(d.get("price", 0.0))
        prev_close = _safe_float(d.get("prev_close", 0.0))
        year_high = _safe_float(d.get("year_high", 0.0))
        year_low = _safe_float(d.get("year_low", 0.0))

        # 3) Argaam fallback ONLY (حسب طلبك)
        if price <= 0:
            p2 = fetch_price_from_argaam(raw_sym)
            if p2 > 0:
                price = p2
                if prev_close <= 0:
                    prev_close = p2  # fallback بسيط

        results[raw_sym] = {
            "price": price,
            "prev_close": prev_close,
            "year_high": year_high,
            "year_low": year_low,
            "source": "yahoo" if _safe_float(d.get("price", 0.0)) > 0 else ("argaam" if price > 0 else "none"),
        }

        # كذلك نخزن نفس البيانات تحت مفاتيح بديلة لتفادي أي mismatch
        for v in _symbol_variants(raw_sym):
            results.setdefault(v, results[raw_sym])

    return results


# ============================================================
# 🧾 Static Info (Fix: return dict for AI Engine)
# ============================================================
def get_static_info(symbol: str) -> dict:
    """
    ✅ مهم للـ AI Engine: يرجع dict فيه sector/name
    """
    sym = get_ticker_symbol(symbol) or str(symbol or "").strip().upper()
    name = sym
    sector = None
    try:
        from data_source import get_company_details
        nm, sec = get_company_details(symbol)
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
# 🔎 Analysis Data Sources Registry (اختياري)
# ============================================================
def get_analysis_sources(symbol: str) -> dict:
    """
    حسب طلبك: مصادر التحليل/الذكاء تكون من:
    Yahoo / Google Finance / TradingView / Argaam / Investing
    هذه دالة مرجعية/تجميع (لا تكسر النظام إذا بعض المصادر فشل).
    """
    sym = get_ticker_symbol(symbol)
    out = {"symbol": sym, "sources": {}}

    # Yahoo snapshot
    out["sources"]["yahoo"] = {
        "price_pack": fetch_price_from_yahoo(sym),
        "ok": True,
    }

    # Google Finance snapshot (تحليل فقط)
    out["sources"]["google_finance"] = fetch_google_finance_snapshot(sym)

    # TradingView / Investing placeholders (تفعيل لاحق إذا رغبت)
    out["sources"]["tradingview"] = fetch_tradingview_snapshot(sym)
    out["sources"]["investing"] = fetch_investing_snapshot(sym)

    # Argaam snapshot (تحليل/احتياط)
    out["sources"]["argaam"] = {
        "price": fetch_price_from_argaam(sym),
        "ok": True,
    }

    return out