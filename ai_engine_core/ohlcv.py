from osoli_logging import log_exception
# ai_engine_core/ohlcv.py

import pandas as pd
import numpy as np

def _ensure_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    يطبع أسماء الأعمدة إلى Open/High/Low/Close/Volume
    ويفك MultiIndex إذا موجود.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    # فك MultiIndex الأعمدة (أحياناً من yfinance)
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(c[-1]) for c in df.columns]
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    cols = {c: c for c in df.columns}
    lower = {str(c).lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
            if n.lower() in lower:
                return lower[n.lower()]
        return None

    m_open = pick("Open", "open", "OPEN")
    m_high = pick("High", "high", "HIGH")
    m_low = pick("Low", "low", "LOW")
    m_close = pick("Close", "close", "Adj Close", "adjclose", "adj_close", "ADJ CLOSE")
    m_vol = pick("Volume", "volume", "VOL", "vol")

    ren = {}
    if m_open and m_open != "Open":
        ren[m_open] = "Open"
    if m_high and m_high != "High":
        ren[m_high] = "High"
    if m_low and m_low != "Low":
        ren[m_low] = "Low"
    if m_close and m_close != "Close":
        ren[m_close] = "Close"
    if m_vol and m_vol != "Volume":
        ren[m_vol] = "Volume"

    if ren:
        df = df.rename(columns=ren)

    # تأكد الأعمدة الأساسية موجودة
    needed = ["Open", "High", "Low", "Close"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"missing {c}")

    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    # تنظيف أنواع البيانات
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    return df


def assess_ohlcv_quality(df: pd.DataFrame, interval: str = "1d") -> dict:
    """Return a pragmatic data-quality report for OHLCV.

    الهدف: حماية المستشار من بيانات ناقصة/مشوهة (NaN/Volume=0/قيم غير منطقية/قفزات).
    يعيد:
      - score: 0..100
      - pass: bool
      - issues: list[str]
      - metrics: dict (للعرض والتشخيص)
    """
    out = {"score": 0, "pass": False, "issues": [], "metrics": {}}
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        out["issues"].append("لا توجد بيانات سعرية (DF فارغ).")
        return out

    # Ensure required columns exist
    required = ["Open", "High", "Low", "Close"]
    for c in required:
        if c not in df.columns:
            out["issues"].append(f"عمود مفقود: {c}")
            return out
    if "Volume" not in df.columns:
        df = df.copy()
        df["Volume"] = 0.0

    d = df[required + ["Volume"]].copy()

    # Basic cleaning stats
    n = int(len(d))
    out["metrics"]["rows"] = n

    # NaN ratios (after coercion, before dropna)
    nan_ratio = {}
    for c in required + ["Volume"]:
        try:
            nan_ratio[c] = float(pd.to_numeric(d[c], errors="coerce").isna().mean())
        except Exception:
            nan_ratio[c] = 1.0
    out["metrics"]["nan_ratio"] = nan_ratio

    # Coerce numeric
    for c in required + ["Volume"]:
        try:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")

    # Drop rows with missing OHLC
    before = len(d)
    d = d.dropna(subset=required).copy()
    dropped = int(before - len(d))
    if dropped > 0:
        out["issues"].append(f"تم إسقاط {dropped} صف بسبب NaN في OHLC.")
    out["metrics"]["dropped_rows"] = dropped
    if d.empty:
        out["issues"].append("البيانات أصبحت فارغة بعد تنظيف NaN.")
        return out

    # Price validity checks
    invalid_price_ratio = float(((d["Open"] <= 0) | (d["High"] <= 0) | (d["Low"] <= 0) | (d["Close"] <= 0)).mean())
    out["metrics"]["invalid_price_ratio"] = invalid_price_ratio
    if invalid_price_ratio > 0:
        out["issues"].append("يوجد أسعار <= 0 (غير منطقية).")

    hl_bad_ratio = float((d["High"] < d["Low"]).mean())
    out["metrics"]["high_lt_low_ratio"] = hl_bad_ratio
    if hl_bad_ratio > 0:
        out["issues"].append("يوجد شموع High < Low (بيانات مشوهة).")

    close_out_ratio = float(((d["Close"] < d["Low"]) | (d["Close"] > d["High"])).mean())
    out["metrics"]["close_outside_hilo_ratio"] = close_out_ratio
    if close_out_ratio > 0:
        out["issues"].append("يوجد Close خارج نطاق High/Low (بيانات مشوهة).")

    # Duplicated index
    try:
        dup_idx = float(pd.Index(d.index).duplicated().mean())
    except Exception:
        dup_idx = 0.0
    out["metrics"]["dup_index_ratio"] = dup_idx
    if dup_idx > 0:
        out["issues"].append("يوجد تكرار في مؤشر الزمن (duplicated index).")

    # Time gaps (if datetime-like index)
    gap_ratio = 0.0
    try:
        idx = pd.to_datetime(d.index, errors="coerce")
        if idx.notna().all():
            # Expected cadence
            tf = str(interval or "1d").lower()
            if tf in ("1d", "1wk", "1mo"):
                expected = pd.Timedelta(days=1 if tf == "1d" else (7 if tf == "1wk" else 30))
            else:
                # intraday minutes
                m = 60
                try:
                    if tf.endswith("m"):
                        m = int(tf[:-1])
                except Exception:
                    m = 60
                expected = pd.Timedelta(minutes=m)

            diffs = pd.Series(idx).diff().dropna()
            if len(diffs) > 0:
                # consider gaps larger than 3x expected
                gap_ratio = float((diffs > (expected * 3)).mean())
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    out["metrics"]["time_gap_ratio"] = gap_ratio
    if gap_ratio > 0.05:
        out["issues"].append("يوجد فجوات زمنية كبيرة في البيانات (time gaps).")

    # Volume zeros
    zero_vol_ratio = 0.0
    try:
        vv = d["Volume"].fillna(0)
        zero_vol_ratio = float((vv <= 0).mean())
    except Exception:
        zero_vol_ratio = 1.0
    out["metrics"]["zero_volume_ratio"] = zero_vol_ratio
    if zero_vol_ratio > 0.35:
        out["issues"].append("نسبة كبيرة من Volume = 0 (جودة الحجم ضعيفة).")

    # Extreme returns / outliers
    extreme_ret_ratio = 0.0
    try:
        ret = d["Close"].pct_change().abs().dropna()
        if len(ret) > 0:
            extreme_ret_ratio = float((ret > 0.40).mean())  # > 40% jump in one bar
    except Exception:
        extreme_ret_ratio = 0.0
    out["metrics"]["extreme_return_ratio"] = extreme_ret_ratio
    if extreme_ret_ratio > 0.02:
        out["issues"].append("قفزات سعرية كبيرة جدًا متكررة (قد تكون بيانات غير نظيفة).")

    # Score aggregation (start at 100 then penalize)
    score = 100.0
    score -= min(60.0, invalid_price_ratio * 200.0)
    score -= min(40.0, hl_bad_ratio * 300.0)
    score -= min(35.0, close_out_ratio * 250.0)
    score -= min(25.0, gap_ratio * 120.0)
    score -= min(35.0, max(0.0, zero_vol_ratio - 0.10) * 80.0)
    score -= min(25.0, extreme_ret_ratio * 200.0)
    score -= min(15.0, dup_idx * 200.0)

    # NaN penalty (for OHLC columns only)
    nan_ohlc = float(np.mean([nan_ratio.get(c, 0.0) for c in required]))
    score -= min(25.0, nan_ohlc * 100.0)

    score = max(0.0, min(100.0, score))
    out["score"] = int(round(score))
    out["pass"] = out["score"] >= 60 and len(d) >= 40 and invalid_price_ratio < 0.05 and hl_bad_ratio == 0.0 and close_out_ratio == 0.0
    return out
