# market_data.py

import re
import time
import json
import os
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
# 🕯️ Twelve Data (OHLCV History)  — بديل Yahoo للتاريخ/الشموع
# ============================================================

def _get_twelvedata_key() -> str:
    try:
        k = st.secrets.get("TWELVEDATA_API_KEY", "")  # type: ignore
        if k:
            return str(k).strip()
    except Exception:
        pass
    return str(os.environ.get("TWELVEDATA_API_KEY", "")).strip()


def _td_interval(interval: str) -> str:
    itv = (interval or "1d").strip().lower()
    mapping = {
        "1d": "1day",
        "1day": "1day",
        "1wk": "1week",
        "1w": "1week",
        "1week": "1week",
        "1mo": "1month",
        "1m": "1month",
        "1month": "1month",
        "1h": "1h",
        "60m": "1h",
        "30m": "30min",
        "15m": "15min",
        "5m": "5min",
        "1m": "1min",
    }
    return mapping.get(itv, "1day")


def _td_request(params: Dict[str, Any], timeout: int = 10, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    if not requests:
        return None
    api_key = _get_twelvedata_key()
    if not api_key:
        return {"ok": False, "error": "missing_api_key"}

    url = "https://api.twelvedata.com/time_series"
    params = dict(params or {})
    params["apikey"] = api_key
    params.setdefault("format", "JSON")

    # Backoff + Throttle (مهم لتجنب 429)
    # نستخدم session_state لتحديد آخر وقت طلب
    now = time.time()
    last = float(st.session_state.get("_td_last_call_ts", 0.0) or 0.0)
    min_gap = float(st.session_state.get("_td_min_gap", 1.2) or 1.2)
    if now - last < min_gap:
        time.sleep(min_gap - (now - last))
    st.session_state["_td_last_call_ts"] = time.time()

    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            # Twelve Data يرسل JSON حتى في الأخطاء
            try:
                data = r.json()
            except Exception:
                data = {"ok": False, "status": r.status_code, "text": (r.text or "")[:300]}

            # Success structure عادة يحتوي "values"
            if isinstance(data, dict) and data.get("values"):
                return data

            status = int(getattr(r, "status_code", 0) or 0)
            msg = ""
            try:
                msg = str(data.get("message") or data.get("error") or "")
            except Exception:
                msg = ""

            # 429 or temp errors -> backoff
            if status in (429, 500, 502, 503, 504) or ("rate" in msg.lower()):
                sleep_s = min(8.0, 1.5 * (2 ** attempt))
                time.sleep(sleep_s)
                continue

            return data if isinstance(data, dict) else None
        except Exception:
            time.sleep(min(6.0, 1.2 * (2 ** attempt)))

    return None


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _td_symbol_search(query: str, exchange: str = "") -> Optional[str]:
    """Resolve a symbol for Twelve Data using symbol_search.
    For Saudi stocks prefer exchange XSAU when possible.
    """
    if not requests:
        return None
    api_key = _get_twelvedata_key()
    if not api_key:
        return None

    q = (query or "").strip()
    if not q:
        return None

    url = "https://api.twelvedata.com/symbol_search"
    params = {"symbol": q, "apikey": api_key}
    if exchange:
        params["exchange"] = exchange

    try:
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        # expected: {"data":[{"symbol":"7203","exchange":"Tadawul",...}, ...]}
        arr = data.get("data") if isinstance(data, dict) else None
        if not isinstance(arr, list) or not arr:
            return None

        # choose best match:
        # 1) exact symbol match
        for row in arr:
            s = str(row.get("symbol") or "").strip()
            if s.upper() == q.upper():
                return s

        # 2) first item
        s0 = str(arr[0].get("symbol") or "").strip()
        return s0 or None
    except Exception:
        return None


def _td_resolve_symbol(symbol: str) -> Optional[str]:
    """Best effort resolve for Saudi stocks + indices."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None

    # Normalizations
    sym = sym.replace("^", "")
    sym = sym.replace(".SR", "")

    # If already numeric code (Saudi stocks) -> search within XSAU
    if sym.isdigit():
        s = _td_symbol_search(sym, exchange="XSAU")
        return s or sym

    # If it's TASI or INDEX
    if sym in ("TASI", "TADAWUL", "TADAWUL ALL SHARE", "TADAWUL ALL SHARE INDEX"):
        s = _td_symbol_search("TASI")
        return s or "TASI"

    # Otherwise attempt search without exchange
    s = _td_symbol_search(sym)
    return s or sym


def _td_values_to_ohlcv(values: List[Dict[str, Any]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    df = pd.DataFrame(values)
    # values come newest->oldest; reverse
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.sort_values("datetime")
        df = df.set_index("datetime")
    rename = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    for k, v in rename.items():
        if k in df.columns and v not in df.columns:
            df[v] = pd.to_numeric(df[k], errors="coerce")
    df = df[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]]
    df = df.dropna(subset=[c for c in ["Open", "High", "Low", "Close"] if c in df.columns], how="any")
    return df


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
    """Best-effort snapshot from TradingView public symbol page.
    ملاحظة: قد تفشل على بعض البيئات بسبب الحماية/الـ Cloudflare.
    """
    sym = str(symbol or "").strip().upper()
    norm = get_ticker_symbol(sym)
    if not norm:
        return {"source": "tradingview", "ok": False, "price": 0.0}

    code = norm.replace(".SR", "").replace("^", "")
    if not code or not code.isdigit():
        return {"source": "tradingview", "ok": False, "price": 0.0}

    url = f"https://www.tradingview.com/symbols/TADAWUL-{code}/"
    r = _http_get(url, timeout=8, retries=1)
    if not r:
        return {"source": "tradingview", "ok": False, "price": 0.0, "url": url}

    text = r.text or ""
    m = re.search(r'property="og:price:amount"\s+content="([0-9]+(?:\.[0-9]+)?)"', text)
    if not m:
        m = re.search(r'"last_price"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
    price = _safe_float(m.group(1)) if m else 0.0
    return {"source": "tradingview", "ok": _is_reasonable_price(price), "price": float(price), "url": url}


def fetch_investing_snapshot(symbol: str) -> Dict[str, Any]:
    """Best-effort snapshot from Investing.com.
    غالبًا يحتاج ربط ID/slug، لذلك نتركه كـ best-effort بسيط.
    """
    return {"source": "investing", "ok": False, "price": 0.0, "note": "Needs symbol mapping (slug)."}


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
    """جلب مؤشر تاسي (TASI) بأولوية Twelve Data ثم بقية المصادر.

    Returns:
      (tasi_value, change_percent)
    """
    # 1) Twelve Data Quote (أفضلية)
    try:
        from twelvedata_provider import get_quote, get_time_series

        q = get_quote("TASI")
        if isinstance(q, dict) and q.get("ok"):
            curr = _safe_float(q.get("price") or 0.0)
            prev = _safe_float(q.get("prev_close") or 0.0)
            chg = _safe_float(q.get("chg_pct") or 0.0)

            # Compute prev/percent from candles if missing
            if (prev <= 0 or chg == 0.0) and curr > 0:
                h = get_time_series("TASI", interval="1d", years=1, outputsize=10)
                if isinstance(h, pd.DataFrame) and not h.empty and "Close" in h.columns:
                    closes = h["Close"].dropna()
                    if len(closes) >= 2:
                        prev = float(closes.iloc[-2])
                        if prev > 0:
                            chg = ((curr - prev) / prev) * 100.0

            if _is_reasonable_price(curr):
                return float(curr), round(_safe_float(chg), 2)
    except Exception:
        pass

    # 2) TradingView best-effort
    try:
        if requests:
            url = "https://www.tradingview.com/symbols/TADAWUL-TASI/"
            r = _http_get(url, timeout=8, retries=1)
            if r:
                txt = r.text or ""
                m2 = re.search(r'property="og:price:amount"\s+content="([0-9]+(?:\.[0-9]+)?)"', txt)
                curr = _safe_float(m2.group(1)) if m2 else 0.0
                if _is_reasonable_price(curr):
                    return float(curr), 0.0
    except Exception:
        pass

    # 3) Yahoo (yfinance) كحل أخير
    try:
        # بعض البيئات تستخدم ^TASI أو ^TASI.SR غير ثابت — نجرب عدة أشكال
        for ysym in ("^TASI", "^TASI.SR", "TASI.SR"):
            try:
                t = yf.Ticker(ysym)
                info = getattr(t, "fast_info", None) or {}
                p = _safe_float(info.get("lastPrice", 0.0) if isinstance(info, dict) else 0.0)
                if _is_reasonable_price(p):
                    return float(p), 0.0
            except Exception:
                continue
    except Exception:
        pass

    return 0.0, 0.0

# ============================================================
# 📉 Chart History (للرسم البياني والذكاء الاصطناعي)
# ============================================================
# ============================================================
# 📉 Chart History (للرسم البياني والذكاء الاصطناعي)
# ============================================================

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_chart_history(symbol: str, period: str = None, interval: str = "1d", years: int = 5) -> pd.DataFrame:
    """جلب شموع OHLCV (يابانية) بأولوية Twelve Data ثم بقية المصادر.

    الهدف: توفير بيانات كافية للرسوم/المؤشرات/المستشار بدون انهيار.
    - Twelve Data أولاً (Daily خام) ثم نقوم بعمل Resample للفواصل Weekly/Monthly لضمان توفر 10+ سنوات عند الحاجة.
    - Yahoo/yfinance كحل أخير فقط.
    """
    sym = get_ticker_symbol(symbol) or str(symbol or "").strip().upper()
    if not sym:
        return pd.DataFrame()

    # Normalize interval
    itv = (interval or "1d").strip().lower()
    if itv in ("d", "1day", "day"):
        itv = "1d"
    if itv in ("w", "1week", "week"):
        itv = "1wk"
    if itv in ("m", "1month", "month"):
        itv = "1mo"

    # Choose span: monthly/weekly require longer history to meet min candles
    years_needed = int(years or 5)
    if itv in ("1wk", "1mo"):
        years_needed = max(years_needed, 15)

    # --- Twelve Data first ---
    df = pd.DataFrame()
    try:
        from twelvedata_provider import get_time_series as td_get_ts

        # Fetch DAILY always then resample if needed
        base = td_get_ts(sym, interval="1d", years=years_needed, outputsize=5000)
        if isinstance(base, pd.DataFrame) and not base.empty:
            df = base.copy()
    except Exception:
        df = pd.DataFrame()

    # Resample for weekly/monthly if needed
    try:
        if isinstance(df, pd.DataFrame) and not df.empty and itv in ("1wk", "1mo"):
            d = df.copy()
            # ensure datetime index
            if not isinstance(d.index, pd.DatetimeIndex):
                if "Date" in d.columns:
                    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
                    d = d.set_index("Date")
                else:
                    d.index = pd.to_datetime(d.index, errors="coerce")
            d = d.sort_index()
            o = d["Open"]
            h = d["High"]
            l = d["Low"]
            c = d["Close"]
            v = d["Volume"] if "Volume" in d.columns else None

            rule = "W-FRI" if itv == "1wk" else "M"
            out = pd.DataFrame(
                {
                    "Open": o.resample(rule).first(),
                    "High": h.resample(rule).max(),
                    "Low": l.resample(rule).min(),
                    "Close": c.resample(rule).last(),
                }
            )
            if v is not None:
                out["Volume"] = v.resample(rule).sum()
            out = out.dropna(subset=["Open", "High", "Low", "Close"])
            df = out
    except Exception:
        pass

    # --- Fallback: yfinance (last resort) ---
    if df is None or df.empty:
        try:
            yf_sym = sym if sym.endswith(".SR") else f"{sym}.SR"
            prd = period or (f"{years_needed}y" if years_needed else "5y")
            d2 = yf.download(yf_sym, period=prd, interval=("1d" if itv in ("1wk", "1mo") else itv), progress=False)
            if isinstance(d2, pd.DataFrame) and not d2.empty:
                d2 = d2.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
                # if need resample
                if itv in ("1wk", "1mo"):
                    d2 = d2.sort_index()
                    rule = "W-FRI" if itv == "1wk" else "M"
                    out = pd.DataFrame(
                        {
                            "Open": d2["Open"].resample(rule).first(),
                            "High": d2["High"].resample(rule).max(),
                            "Low": d2["Low"].resample(rule).min(),
                            "Close": d2["Close"].resample(rule).last(),
                            "Volume": d2["Volume"].resample(rule).sum() if "Volume" in d2.columns else np.nan,
                        }
                    )
                    out = out.dropna(subset=["Open", "High", "Low", "Close"])
                    df = out
                else:
                    df = d2
        except Exception:
            pass

    # Final normalize columns
    if df is None or df.empty:
        return pd.DataFrame()

    # Ensure standard columns exist
    cols = ["Open", "High", "Low", "Close", "Volume"]
    for c in cols:
        if c not in df.columns:
            if c == "Volume":
                df[c] = 0.0
            else:
                df[c] = np.nan
    df = df[cols].copy()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_tasi_history(period: str = None, interval: str = "1d") -> pd.DataFrame:
    # TASI index on Twelve Data is عادة "TASI"
    return get_chart_history("TASI", period=period, interval=interval, years=10)


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
    """جلب الأسعار (Snapshot) بأولوية Twelve Data ثم بقية المصادر.

    الترتيب:
    1) Twelve Data (Quote/آخر إغلاق)  ✅
    2) Google Finance
    3) TradingView
    4) Investing
    5) Argaam
    6) Yahoo (yfinance) كحل أخير جدًا (قد يسبب 429/حظر)
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not symbols_list:
        return results

    # Try import Twelve Data provider
    try:
        from twelvedata_provider import get_quote as td_get_quote, get_time_series as td_get_ts
    except Exception:
        td_get_quote, td_get_ts = None, None

    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    for raw_sym in input_symbols:
        norm = get_ticker_symbol(raw_sym) or raw_sym

        price = 0.0
        prev_close = 0.0
        year_high = 0.0
        year_low = 0.0
        source = "failed"

        # 1) Twelve Data (أفضلية)
        if td_get_quote:
            try:
                q = td_get_quote(norm)
                if isinstance(q, dict) and q.get("ok"):
                    p = _safe_float(q.get("price", 0.0))
                    pc = _safe_float(q.get("prev_close", 0.0))
                    if _is_reasonable_price(p):
                        price = float(p)
                        prev_close = float(pc) if pc > 0 else float(p)
                        source = "twelvedata"
            except Exception:
                pass

            # لو prev_close غير متوفر نحسبه من آخر شمعتين
            if price > 0 and prev_close <= 0 and td_get_ts:
                try:
                    h = td_get_ts(norm, interval="1d", years=1, outputsize=10)
                    if isinstance(h, pd.DataFrame) and not h.empty and "Close" in h.columns:
                        closes = h["Close"].dropna()
                        if len(closes) >= 2:
                            prev_close = float(closes.iloc[-2])
                except Exception:
                    pass

        # 2) Google Finance
        if price <= 0:
            g = fetch_google_finance_snapshot(norm) or {}
            p = _safe_float(g.get("price", 0.0))
            if _is_reasonable_price(p):
                price = float(p)
                prev_close = float(_safe_float(g.get("prev_close", p))) or float(p)
                year_high = float(_safe_float(g.get("year_high", 0.0)))
                year_low = float(_safe_float(g.get("year_low", 0.0)))
                source = "google_finance"

        # 3) TradingView
        if price <= 0:
            tv = fetch_tradingview_snapshot(norm) or {}
            p = _safe_float(tv.get("price", 0.0))
            if _is_reasonable_price(p):
                price = float(p)
                prev_close = float(_safe_float(tv.get("prev_close", p))) or float(p)
                source = "tradingview"

        # 4) Investing
        if price <= 0:
            inv = fetch_investing_snapshot(norm) or {}
            p = _safe_float(inv.get("price", 0.0))
            if _is_reasonable_price(p):
                price = float(p)
                prev_close = float(_safe_float(inv.get("prev_close", p))) or float(p)
                source = "investing"

        # 5) Argaam
        if price <= 0:
            ar = fetch_argaam_snapshot(norm) or {}
            p = _safe_float(ar.get("price", 0.0))
            if _is_reasonable_price(p):
                price = float(p)
                prev_close = float(_safe_float(ar.get("prev_close", p))) or float(p)
                source = "argaam"

        # 6) Yahoo (yfinance) آخر شيء
        if price <= 0:
            try:
                yf_sym = norm if norm.endswith(".SR") else f"{norm}.SR"
                t = yf.Ticker(yf_sym)
                info = getattr(t, "fast_info", None) or {}
                p = _safe_float(info.get("lastPrice", 0.0) if isinstance(info, dict) else 0.0)
                if _is_reasonable_price(p):
                    price = float(p)
                    prev_close = float(price)
                    source = "yahoo_yfinance"
            except Exception:
                pass

        change_pct = 0.0
        if prev_close > 0 and price > 0:
            change_pct = ((price - prev_close) / prev_close) * 100.0

        results[norm] = {
            "symbol": norm,
            "price": float(price) if price else 0.0,
            "previous_close": float(prev_close) if prev_close else 0.0,
            "change_percent": float(round(_safe_float(change_pct), 2)) if price and prev_close else 0.0,
            "year_high": float(year_high) if year_high else 0.0,
            "year_low": float(year_low) if year_low else 0.0,
            "source": source,
        }

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

    out["sources"]["yahoo"] = {"ok": False, "note": "Disabled for prices (used only for statements)."}
    out["sources"]["google_finance"] = fetch_google_finance_snapshot(sym)
    out["sources"]["tradingview"] = fetch_tradingview_snapshot(sym)
    out["sources"]["investing"] = fetch_investing_snapshot(sym)

    p_argaam = fetch_price_from_argaam(sym)
    out["sources"]["argaam"] = {"price": p_argaam, "ok": _is_reasonable_price(p_argaam)}

    out["sources"]["vs_tasi"] = get_relative_strength_vs_tasi(sym, period=None, interval="1d")

    return out
