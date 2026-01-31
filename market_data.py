# market_data.py
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
# 🌐 HTTP Safety (تأمين الاتصال)
# ============================================================
# استخدام User-Agent حديث لتجنب حظر السكرابينج من المواقع
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

# Session ثابت (أخف + أسرع + يحفظ الكوكيز)
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def _http_get(url: str, timeout: int = 5, retries: int = 2, sleep: float = 0.5):
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
            # معالجة أخطاء 429 (Too Many Requests)
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
    # إذا كان رقماً فقط (مثل 1120) نضيف .SR
    if s.isdigit():
        return f"{s}.SR"
    # إذا لم ينته بـ .SR ولم يبدأ بـ ^ (للمؤشرات العالمية)
    if not s.endswith(".SR") and not s.startswith("^") and not s.startswith("SAR"):
        return f"{s}.SR"
    return s


def _symbol_variants(symbol: str) -> list[str]:
    """
    مفاتيح محتملة لنفس الرمز لتجنب mismatch بين أجزاء النظام.
    مثال: 1120 قد تطلب كـ 1120.SR أو 1120
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

    # إزالة التكرار مع الحفاظ على الترتيب
    out, seen = [], set()
    for x in variants:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _safe_float(val) -> float:
    """تحويل آمن للأرقام"""
    try:
        if val is None:
            return 0.0
        # إزالة الفواصل والنصوص غير الرقمية
        if isinstance(val, str):
            val = val.replace(',', '').replace('SAR', '').strip()
        return float(val)
    except Exception:
        return 0.0


def _is_reasonable_price(x: float) -> bool:
    """
    فلتر معقولية: يمنع التقاط أرقام عشوائية من scraping.
    """
    try:
        x = float(x)
        # سعر سهم/مؤشر منطقي (بين هللة و 30 ألف ريال)
        return 0.01 < x < 30000
    except Exception:
        return False


# ============================================================
# 🧱 OHLCV Normalizer (Fix MultiIndex/Tuple Columns)
# ============================================================
def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    ✅ الوظيفة الأهم: تنظيف بيانات yfinance
    - تعالج MultiIndex columns 
    - توحد أسماء الأعمدة (Open, High, Low, Close)
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # 1. معالجة MultiIndex (يحدث عند تحميل عدة أسهم أو الإصدارات الجديدة)
    if isinstance(df.columns, pd.MultiIndex):
        # نحاول أخذ المستوى الذي يحتوي على أسماء الأعمدة (Open, Close...)
        # غالباً هو المستوى 0، ولكن نتأكد
        df.columns = df.columns.get_level_values(0)

    # 2. تحويل الأسماء إلى String
    df.columns = [str(c[0] if isinstance(c, (tuple, list)) and len(c) else c) for c in df.columns]

    # 3. توحيد الأسماء (Case Insensitive)
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
        if key in canonical:
            rename_map[col] = canonical[key]
    
    df.rename(columns=rename_map, inplace=True)

    # 4. Fallbacks (إذا نقص عمود نحاول تعويضه)
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df["Close"] = df["Adj Close"]

    if "Open" not in df.columns and "Close" in df.columns:
        df["Open"] = df["Close"]

    # 5. التأكد من نوع البيانات (Numeric)
    cols_to_numeric = ["Open", "High", "Low", "Close", "Volume"]
    for c in cols_to_numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 6. حذف الصفوف الفارغة الضرورية
    needed = ["Open", "High", "Low", "Close"]
    valid_cols = [c for c in needed if c in df.columns]
    
    if not valid_cols:
        return pd.DataFrame() # فشل في إيجاد أعمدة الأسعار

    df = df.dropna(subset=valid_cols, how='all')

    # 7. ترتيب التاريخ
    try:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()
        else:
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
    except Exception:
        pass

    return df


# ============================================================
# 📈 Google Finance (Snapshot)
# ============================================================
def fetch_google_finance_snapshot(symbol: str) -> dict:
    """مصدر مساعد للتحليل (Snapshot فقط)"""
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
        # كلاسات Google Finance تتغير باستمرار، لذا هذا الجزء قد يحتاج تحديث دوري
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
# 📊 TradingView / Investing (Placeholders)
# ============================================================
def fetch_tradingview_snapshot(symbol: str) -> dict:
    """Helper للتحليل فقط — مغلق حالياً للحماية"""
    return {"source": "tradingview", "ok": False, "note": "Disabled by default."}


def fetch_investing_snapshot(symbol: str) -> dict:
    """Helper للتحليل فقط — مغلق حالياً للحماية"""
    return {"source": "investing", "ok": False, "note": "Disabled by default."}


# ============================================================
# 🟦 Argaam (أرقام) - المصدر الاحتياطي القوي
# ============================================================
def _extract_argaam_price_from_html(html: str) -> float:
    """استخراج السعر من HTML موقع أرقام بطرق متعددة"""
    if not html:
        return 0.0

    soup = BeautifulSoup(html, "html.parser")

    # 1) Meta tags (الأكثر دقة)
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

    # 2) JSON patterns (Regex)
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

    # 3) البحث المباشر في النص (مخاطرة أقل دقة)
    # نبحث عن نمط السعر داخل عنصر span له كلاسات معتادة في أرقام
    price_spans = soup.find_all("span", class_=re.compile("price|value|last"))
    for span in price_spans:
        p = _safe_float(span.text)
        if _is_reasonable_price(p):
            return p

    return 0.0


def fetch_price_from_argaam(symbol: str) -> float:
    """
    ✅ المصدر الاحتياطي لتحديث الأسعار
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return 0.0

    code = s.replace(".SR", "").replace("^", "")
    if not code.isdigit():
        return 0.0

    # قائمة روابط محتملة (عربي وإنجليزي)
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
def fetch_price_from_yahoo(symbol: str) -> dict:
    """
    جلب بيانات فورية لسهم واحد
    يرجع: price, prev_close, year_high, year_low
    """
    sym = get_ticker_symbol(symbol)
    default_res = {"price": 0.0, "prev_close": 0.0, "year_high": 0.0, "year_low": 0.0}
    
    if not sym:
        return default_res

    try:
        t = yf.Ticker(sym)
        # محاولة استخدام fast_info (الأسرع والأدق حالياً)
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

        # Fallback: استخدام history إذا فشل fast_info
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
    """جلب بيانات المؤشر العام (كاش 5 دقائق)"""
    try:
        tick = yf.Ticker("^TASI.SR")
        fi = tick.fast_info
        curr = _safe_float(getattr(fi, "last_price", None))
        prev = _safe_float(getattr(fi, "previous_close", None))
        
        # إذا فشل fast_info نحاول الـ history
        if curr <= 0:
             hist = tick.history(period="2d")
             if len(hist) > 0:
                 curr = hist["Close"].iloc[-1]
                 prev = hist["Close"].iloc[-2] if len(hist) > 1 else curr

        if _is_reasonable_price(curr):
            chg = 0.0
            if prev > 0:
                chg = ((curr - prev) / prev) * 100.0
            return curr, round(_safe_float(chg), 2)
    except Exception:
        pass

    # Fallback: Google Finance
    snap = fetch_google_finance_snapshot(".TASI")
    p = _safe_float(snap.get("price", 0.0))
    return (p if _is_reasonable_price(p) else 0.0), 0.0


# ============================================================
# 📉 Chart History (للرسم البياني والذكاء الاصطناعي)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_chart_history(symbol: str, period: str = "2y", interval: str = "1d"):
    """
    جلب البيانات التاريخية للرسوم البيانية
    """
    sym = get_ticker_symbol(symbol)
    if not sym:
        return pd.DataFrame()

    try:
        # download أسرع من Ticker.history عند طلب فترات طويلة
        df = yf.download(
            sym,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False # False أحياناً يكون أكثر استقراراً في Streamlit Cloud
        )
    except Exception:
        return pd.DataFrame()

    return _normalize_ohlcv_columns(df)


# ============================================================
# 💹 Batch Prices (تحديث جماعي للمحفظة)
# ============================================================
@st.cache_data(ttl=120, show_spinner=False)
def fetch_batch_data(symbols_list: list):
    """
    ✅ الوظيفة الرئيسية لتحديث المحفظة:
    - تحاول جلب الكل مرة واحدة عبر Yahoo (أسرع شيء).
    - أي سهم يفشل، تحاول جلبه فردياً من Argaam.
    """
    results = {}
    if not symbols_list:
        return results

    # 1. تنظيف المدخلات
    input_symbols = [str(s).strip().upper() for s in symbols_list if str(s).strip()]
    norm_map = {s: get_ticker_symbol(s) for s in input_symbols}
    
    # قائمة الرموز الفريدة الموحدة (Unique Normalized Symbols)
    clean_syms = sorted(list(set([v for v in norm_map.values() if v])))
    
    yahoo_data_by_norm = {}

    # 2. محاولة الجلب الجماعي (Yahoo Batch)
    try:
        if len(clean_syms) == 1:
            sym = clean_syms[0]
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)
        else:
            # Tickers object يتيح الوصول لبيانات متعددة
            tickers = yf.Tickers(" ".join(clean_syms))
            for sym in clean_syms:
                try:
                    # الوصول لـ ticker الفرعي
                    sub_ticker = tickers.tickers[sym]
                    fi = getattr(sub_ticker, "fast_info", None)
                    
                    price = _safe_float(getattr(fi, "last_price", 0.0))
                    prev_close = _safe_float(getattr(fi, "previous_close", 0.0))
                    
                    # إذا نجح الجلب
                    if _is_reasonable_price(price):
                        yahoo_data_by_norm[sym] = {
                            "price": price,
                            "prev_close": prev_close,
                            "year_high": _safe_float(getattr(fi, "year_high", 0.0)),
                            "year_low": _safe_float(getattr(fi, "year_low", 0.0)),
                        }
                    else:
                        # نضع علامة للفشل ليتم استخدام Argaam لاحقاً
                        yahoo_data_by_norm[sym] = {"price": 0.0}
                except Exception:
                    yahoo_data_by_norm[sym] = {"price": 0.0}
    except Exception:
        # في حال فشل الـ Batch بالكامل، نجرب فردي (نادر الحدوث)
        for sym in clean_syms:
            yahoo_data_by_norm[sym] = fetch_price_from_yahoo(sym)

    # 3. بناء النتيجة النهائية مع Fallback لـ Argaam
    for raw_sym in input_symbols:
        norm = norm_map.get(raw_sym) or get_ticker_symbol(raw_sym)
        
        # البيانات المبدئية من Yahoo
        d = yahoo_data_by_norm.get(norm, {"price": 0.0, "prev_close": 0.0})
        
        price = _safe_float(d.get("price", 0.0))
        prev_close = _safe_float(d.get("prev_close", 0.0))
        year_high = _safe_float(d.get("year_high", 0.0))
        year_low = _safe_float(d.get("year_low", 0.0))
        source = "yahoo"

        # Argaam Fallback: إذا السعر صفر، جرب أرقام
        if price <= 0:
            p2 = fetch_price_from_argaam(raw_sym)
            if _is_reasonable_price(p2):
                price = float(p2)
                # إذا لم نجد إغلاق سابق، نفترضه نفس السعر مؤقتاً لتجنب خطأ القسمة
                if prev_close <= 0:
                    prev_close = float(p2)
                source = "argaam"
            else:
                source = "failed"

        # تخزين النتيجة
        res_entry = {
            "price": price,
            "prev_close": prev_close,
            "year_high": year_high,
            "year_low": year_low,
            "source": source,
        }
        
        results[raw_sym] = res_entry

        # تخزين نسخ إضافية للمفاتيح المحتملة (Variants)
        # لضمان أنه لو طلب النظام "1120" أو "1120.SR" يجد النتيجة
        for v in _symbol_variants(raw_sym):
            results.setdefault(v, res_entry)

    return results


# ============================================================
# 🧾 Static Info (بيانات ثابتة للمحرك الذكي)
# ============================================================
def get_static_info(symbol: str) -> dict:
    """
    يرجع معلومات الشركة (الاسم، القطاع).
    مصمم ليكون آمناً ولا يكسر التطبيق إذا لم تتوفر البيانات.
    """
    sym = get_ticker_symbol(symbol) or str(symbol or "").strip().upper()
    name = sym
    sector = "Unknown"

    try:
        # استيراد داخلي لتجنب Circular Import مع data_source.py
        from data_source import get_company_details
        
        info = get_company_details(symbol)

        if isinstance(info, dict):
            name = info.get("name") or info.get("Name") or name
            sector = info.get("sector") or info.get("Sector") or sector
        elif isinstance(info, (list, tuple)) and len(info) >= 2:
            nm, sec = info
            if nm: name = nm
            if sec: sector = sec
    except Exception:
        pass

    return {
        "symbol": sym,
        "name": name,
        "sector": sector,
        "source": "data_source",
    }


# ============================================================
# 🔎 Analysis Registry (مجمع المصادر للتحليل)
# ============================================================
def get_analysis_sources(symbol: str) -> dict:
    """
    يجمع كل البيانات المتاحة عن السهم من كل المصادر (للتحليل العميق).
    """
    sym = get_ticker_symbol(symbol)
    out = {"symbol": sym, "sources": {}}

    # نجمع البيانات ولا نعتمد عليها للتسعير
    out["sources"]["yahoo"] = {"price_pack": fetch_price_from_yahoo(sym), "ok": True}
    out["sources"]["google_finance"] = fetch_google_finance_snapshot(sym)
    out["sources"]["tradingview"] = fetch_tradingview_snapshot(sym)
    out["sources"]["investing"] = fetch_investing_snapshot(sym)
    
    # أرقام كمصدر بيانات
    p_argaam = fetch_price_from_argaam(sym)
    out["sources"]["argaam"] = {"price": p_argaam, "ok": _is_reasonable_price(p_argaam)}

    return out
