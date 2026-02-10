# technical_indicators/advanced.py
# -*- coding: utf-8 -*-

"""
Advanced Technical Indicators (Python implementations inspired by common quant ideas).

IMPORTANT:
- This file implements indicator *ideas* in Python from scratch.
- It does NOT copy proprietary PineScript code verbatim.
- Outputs are standardized for integration into Osoli Score + AI Engine.

Each indicator returns a dict with:
{
  "name": "...",
  "features": {...},
  "signals": [...],
  "evidence": [...],
  "confidence": 0..100,
  "errors": [...]
}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ----------------------------
# Helpers
# ----------------------------

def _col(df: pd.DataFrame, name: str) -> pd.Series:
    if name in df.columns:
        return df[name].astype(float)
    # Support yfinance style columns: 'Open', 'High', 'Low', 'Close', 'Volume'
    for alt in [name.lower(), name.capitalize(), name.upper()]:
        if alt in df.columns:
            return df[alt].astype(float)
    raise KeyError(f"Missing column: {name}")


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        return float(x)
    except Exception:
        return default


def _rolling_pivots(series: pd.Series, left: int = 3, right: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """
    Very simple pivot detector:
    - pivot high: greater than left/right neighbors
    - pivot low:  less than left/right neighbors
    Returns boolean arrays (same length as series).
    """
    n = len(series)
    ph = np.zeros(n, dtype=bool)
    pl = np.zeros(n, dtype=bool)
    v = series.values
    for i in range(left, n - right):
        window = v[i - left : i + right + 1]
        c = v[i]
        if np.all(c >= window) and np.any(c > window):
            ph[i] = True
        if np.all(c <= window) and np.any(c < window):
            pl[i] = True
    return ph, pl


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    if span <= 1:
        return values.astype(float)
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    if len(close) < period + 2:
        return np.full_like(close, np.nan, dtype=float)

    delta = np.diff(close, prepend=close[0])
    gain = np.clip(delta, 0, None)
    loss = np.clip(-delta, 0, None)

    avg_gain = _ema(gain, period)
    avg_loss = _ema(loss, period)

    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ----------------------------
# 1) RLS Forecast (Recursive Least Squares)
# ----------------------------

def rls_forecast(
    df: pd.DataFrame,
    lam: float = 0.995,
    init_delta: float = 1000.0,
    band_mult: float = 1.7,
) -> Dict[str, Any]:
    """
    RLS on linear model y = w0 + w1*t where t is index (0..n-1).
    Provides mean line + uncertainty bands estimated from EWMA of squared errors.
    Also provides mean-reversion signals when price breaks band then closes back inside.
    """
    errors: List[str] = []
    try:
        close = _col(df, "Close").values.astype(float)
        high = _col(df, "High").values.astype(float)
        low = _col(df, "Low").values.astype(float)
    except Exception as e:
        return {
            "name": "RLS Forecast",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": [str(e)],
        }

    n = len(close)
    if n < 30:
        return {
            "name": "RLS Forecast",
            "features": {},
            "signals": [],
            "evidence": ["بيانات قليلة جدًا لحساب RLS بشكل موثوق."],
            "confidence": 10,
            "errors": [],
        }

    # RLS init
    w = np.zeros(2, dtype=float)  # [w0, w1]
    P = np.eye(2, dtype=float) * init_delta

    rls_mean = np.full(n, np.nan, dtype=float)
    msqe = 0.0
    std = np.full(n, np.nan, dtype=float)

    for i in range(n):
        x = np.array([1.0, float(i)], dtype=float)  # [1, t]
        y_hat = float(x @ w)
        y = float(close[i])
        e = y - y_hat

        # Gain vector
        denom = lam + float(x.T @ P @ x)
        if denom <= 0:
            denom = 1e-12
        k = (P @ x) / denom

        # Update
        w = w + k * e
        P = (P - np.outer(k, x.T @ P)) / lam

        rls_mean[i] = float(x @ w)

        # EWMA of error^2
        msqe = lam * msqe + (1 - lam) * (e * e)
        std[i] = float(np.sqrt(max(msqe, 0.0)))

    upper = rls_mean + band_mult * std
    lower = rls_mean - band_mult * std

    # Mean reversion flags
    overbought = high > upper
    oversold = low < lower

    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)

    for i in range(1, n):
        # buy: was oversold then close back above lower band
        if oversold[i - 1] and close[i] > lower[i]:
            buy[i] = True
        # sell: was overbought then close back below upper band
        if overbought[i - 1] and close[i] < upper[i]:
            sell[i] = True

    signals: List[Dict[str, Any]] = []
    if buy.any():
        idx = int(np.where(buy)[0][-1])
        signals.append({"type": "BUY", "index": idx, "price": _safe_float(close[idx]), "reason": "ارتداد للمتوسط بعد كسر النطاق السفلي"})
    if sell.any():
        idx = int(np.where(sell)[0][-1])
        signals.append({"type": "SELL", "index": idx, "price": _safe_float(close[idx]), "reason": "ارتداد للمتوسط بعد كسر النطاق العلوي"})

    slope = _safe_float(w[1])
    band_width = _safe_float((upper[-1] - lower[-1]) if np.isfinite(upper[-1]) and np.isfinite(lower[-1]) else 0.0)

    evidence: List[str] = []
    if abs(slope) > 0:
        evidence.append(f"ميل RLS (Trend slope) ≈ {slope:.6f}")
    if band_width > 0:
        evidence.append(f"عرض نطاق عدم اليقين ≈ {band_width:.3f}")

    conf = 55
    if n >= 120:
        conf += 10
    if band_width > 0 and band_width / max(_safe_float(close[-1], 1.0), 1.0) < 0.05:
        conf += 5  # tighter bands => more stable
    conf = int(max(0, min(100, conf)))

    return {
        "name": "RLS Forecast",
        "features": {
            "rls_slope": slope,
            "band_width": band_width,
            "close": _safe_float(close[-1]),
            "upper": _safe_float(upper[-1]),
            "lower": _safe_float(lower[-1]),
        },
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": errors,
        "series": {
            "rls_mean": rls_mean.tolist(),
            "upper_band": upper.tolist(),
            "lower_band": lower.tolist(),
        },
    }


# ----------------------------
# 2) Chaos-Weighted RSI
# ----------------------------

def chaos_weighted_rsi(
    df: pd.DataFrame,
    period: int = 14,
    chaos_window: int = 30,
    min_span: int = 2,
    max_span: int = 10,
) -> Dict[str, Any]:
    """
    RSI with adaptive smoothing based on a simple 'chaos' proxy:
    - chaos ~ normalized rolling std of returns (0..1)
    - smoothing span changes with chaos (more chaos => more smoothing).
    """
    try:
        close = _col(df, "Close").values.astype(float)
    except Exception as e:
        return {
            "name": "Chaos Weighted RSI",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": [str(e)],
        }

    n = len(close)
    if n < max(period + 5, chaos_window + 5):
        return {
            "name": "Chaos Weighted RSI",
            "features": {},
            "signals": [],
            "evidence": ["بيانات قليلة جدًا لحساب WRSI بشكل موثوق."],
            "confidence": 10,
            "errors": [],
        }

    rsi_raw = _rsi(close, period=period)

    # chaos proxy
    rets = np.diff(close, prepend=close[0])
    rets = np.divide(rets, close, out=np.zeros_like(rets), where=close != 0)
    chaos_std = pd.Series(rets).rolling(chaos_window).std().fillna(0.0).values
    # normalize to 0..1
    cmin, cmax = float(np.min(chaos_std)), float(np.max(chaos_std))
    if cmax - cmin < 1e-12:
        chaos = np.zeros_like(chaos_std, dtype=float)
    else:
        chaos = (chaos_std - cmin) / (cmax - cmin)

    # adaptive smoothing span
    spans = (min_span + (max_span - min_span) * chaos).astype(int)
    spans = np.clip(spans, min_span, max_span)

    wrsi = np.empty_like(rsi_raw, dtype=float)
    wrsi[:] = np.nan
    wrsi[0] = rsi_raw[0] if np.isfinite(rsi_raw[0]) else 50.0

    # one-pass adaptive EMA
    prev = wrsi[0]
    for i in range(1, n):
        span = int(spans[i])
        alpha = 2.0 / (span + 1.0)
        val = rsi_raw[i]
        if not np.isfinite(val):
            val = prev
        prev = alpha * val + (1 - alpha) * prev
        wrsi[i] = prev

    # signals + simple divergence using pivots on close and wrsi
    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []

    last = _safe_float(wrsi[-1], 50.0)
    chaos_last = _safe_float(chaos[-1], 0.0)

    if last < 30:
        signals.append({"type": "BUY", "kind": "OVERSOLD", "value": last, "reason": "WRSI أقل من 30 (تشبع بيع)"})
    elif last > 70:
        signals.append({"type": "SELL", "kind": "OVERBOUGHT", "value": last, "reason": "WRSI أعلى من 70 (تشبع شراء)"})

    # Divergences (basic)
    ph_c, pl_c = _rolling_pivots(pd.Series(close), 3, 3)
    ph_r, pl_r = _rolling_pivots(pd.Series(wrsi), 3, 3)

    # find last 2 pivots for bullish/bearish divergence
    lows = np.where(pl_c)[0]
    highs = np.where(ph_c)[0]

    if len(lows) >= 2:
        i1, i2 = int(lows[-2]), int(lows[-1])
        # bullish: price makes lower low, wrsi makes higher low
        if close[i2] < close[i1] and wrsi[i2] > wrsi[i1]:
            signals.append({"type": "BUY", "kind": "DIVERGENCE_BULL", "index": i2, "reason": "دايفرجنس إيجابي (سعر أدنى + WRSI أعلى)"})

    if len(highs) >= 2:
        i1, i2 = int(highs[-2]), int(highs[-1])
        # bearish: price makes higher high, wrsi makes lower high
        if close[i2] > close[i1] and wrsi[i2] < wrsi[i1]:
            signals.append({"type": "SELL", "kind": "DIVERGENCE_BEAR", "index": i2, "reason": "دايفرجنس سلبي (سعر أعلى + WRSI أدنى)"})

    evidence.append(f"WRSI الحالي ≈ {last:.2f}")
    evidence.append(f"مؤشر الفوضى (chaos) الحالي ≈ {chaos_last:.2f}")

    conf = 55
    # more stable when chaos low
    conf += int((1.0 - chaos_last) * 15)
    conf = int(max(0, min(100, conf)))

    return {
        "name": "Chaos Weighted RSI",
        "features": {
            "wrsi": last,
            "chaos": chaos_last,
            "is_overbought": float(last > 70),
            "is_oversold": float(last < 30),
        },
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": [],
        "series": {
            "wrsi": wrsi.tolist(),
            "chaos": chaos.tolist(),
        },
    }


# ----------------------------
# 3) Volume Profile Clusters (price buckets)
# ----------------------------

@dataclass
class _VPCluster:
    low: float
    high: float
    volume: float
    poc: float


def volume_profile_clusters(
    df: pd.DataFrame,
    n_clusters: int = 12,
) -> Dict[str, Any]:
    """
    Simple clustered volume profile:
    - Split price range into n buckets
    - Aggregate volume into each bucket based on typical price (HLCC/4)
    - POC per bucket approximated as bucket mid
    """
    try:
        high = _col(df, "High").values.astype(float)
        low = _col(df, "Low").values.astype(float)
        close = _col(df, "Close").values.astype(float)
        vol = _col(df, "Volume").values.astype(float)
    except Exception as e:
        return {
            "name": "Clusters Volume Profile",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": [str(e)],
        }

    n = len(close)
    if n < 60:
        return {
            "name": "Clusters Volume Profile",
            "features": {},
            "signals": [],
            "evidence": ["بيانات قليلة جدًا لحساب Volume Profile بشكل موثوق."],
            "confidence": 10,
            "errors": [],
        }

    # typical price
    tp = (high + low + close + close) / 4.0

    pmin = float(np.nanmin(tp))
    pmax = float(np.nanmax(tp))
    if not np.isfinite(pmin) or not np.isfinite(pmax) or (pmax - pmin) <= 0:
        return {
            "name": "Clusters Volume Profile",
            "features": {},
            "signals": [],
            "evidence": ["تعذر بناء نطاق سعري صالح."],
            "confidence": 0,
            "errors": [],
        }

    edges = np.linspace(pmin, pmax, n_clusters + 1)
    vols = np.zeros(n_clusters, dtype=float)

    idx = np.searchsorted(edges, tp, side="right") - 1
    idx = np.clip(idx, 0, n_clusters - 1)

    for i in range(n):
        if np.isfinite(vol[i]):
            vols[idx[i]] += float(vol[i])

    clusters: List[_VPCluster] = []
    for i in range(n_clusters):
        lo = float(edges[i])
        hi = float(edges[i + 1])
        v = float(vols[i])
        poc = float((lo + hi) / 2.0)
        clusters.append(_VPCluster(low=lo, high=hi, volume=v, poc=poc))

    total_vol = float(np.sum(vols))
    if total_vol <= 0:
        total_vol = 1.0

    # Find top POC zones
    top_idx = np.argsort(vols)[::-1][:3]
    top_pocs = [clusters[i].poc for i in top_idx]

    last_close = float(close[-1])

    evidence = [
        f"إجمالي حجم (تقريبي) داخل الشرائح: {total_vol:.0f}",
        f"أقوى مناطق POC (3): " + ", ".join([f\"{p:.2f}\" for p in top_pocs]),
    ]

    # signals: price near a POC zone
    signals: List[Dict[str, Any]] = []
    for p in top_pocs:
        if abs(last_close - p) / max(last_close, 1.0) < 0.01:
            signals.append({"type": "INFO", "kind": "NEAR_POC", "poc": p, "reason": "السعر قريب من منطقة سيولة/تداول مرتفع (POC)"})

    # distribution/accumulation hint (very rough)
    strongest = int(top_idx[0])
    poc_strong = clusters[strongest].poc
    if last_close > poc_strong:
        signals.append({"type": "INFO", "kind": "ABOVE_MAIN_POC", "reason": "السعر أعلى من أقوى POC (ميل إيجابي/دعم محتمل)"})
    elif last_close < poc_strong:
        signals.append({"type": "INFO", "kind": "BELOW_MAIN_POC", "reason": "السعر أسفل أقوى POC (مقاومة محتملة/ضغط بيعي)"})

    # confidence grows with amount of history
    conf = 55
    if n >= 200:
        conf += 10
    conf = int(max(0, min(100, conf)))

    # pack clusters as rows
    rows = []
    for c in clusters:
        rows.append({
            "price_low": c.low,
            "price_high": c.high,
            "poc": c.poc,
            "volume": c.volume,
            "volume_share": (c.volume / total_vol),
        })

    return {
        "name": "Clusters Volume Profile",
        "features": {
            "main_poc": _safe_float(poc_strong),
            "close": _safe_float(last_close),
        },
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": [],
        "clusters": rows,
    }


# ----------------------------
# 4) Trendline Breakout Navigator (simple)
# ----------------------------

def trendline_breakout(
    df: pd.DataFrame,
    pivot_left: int = 3,
    pivot_right: int = 3,
    lookback: int = 120,
) -> Dict[str, Any]:
    """
    Very lightweight automatic trendline breakout logic:
    - detect pivot highs/lows
    - fit line using last 2 pivots (support/resistance)
    - breakout when close crosses line; retest when price touches line again
    """
    try:
        close = _col(df, "Close")
        high = _col(df, "High")
        low = _col(df, "Low")
    except Exception as e:
        return {
            "name": "Trendline Breakout",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": [str(e)],
        }

    n = len(close)
    if n < 60:
        return {
            "name": "Trendline Breakout",
            "features": {},
            "signals": [],
            "evidence": ["بيانات قليلة جدًا لحساب الترندلاين بشكل موثوق."],
            "confidence": 10,
            "errors": [],
        }

    # limit
    start = max(0, n - lookback)
    c = close.iloc[start:].reset_index(drop=True)
    h = high.iloc[start:].reset_index(drop=True)
    l = low.iloc[start:].reset_index(drop=True)

    ph, pl = _rolling_pivots(c, pivot_left, pivot_right)
    highs = np.where(ph)[0]
    lows = np.where(pl)[0]

    signals: List[Dict[str, Any]] = []
    evidence: List[str] = []
    features: Dict[str, Any] = {}

    # resistance trendline from last two pivot highs
    if len(highs) >= 2:
        i1, i2 = int(highs[-2]), int(highs[-1])
        y1, y2 = float(h.iloc[i1]), float(h.iloc[i2])
        if i2 != i1:
            m = (y2 - y1) / (i2 - i1)
            b = y2 - m * i2
            x_last = len(c) - 1
            line_last = m * x_last + b
            features["res_tl"] = _safe_float(line_last)
            evidence.append(f\"ترند مقاومة من قمم pivots (ميل={m:.4f})\")

            # breakout: close crosses above resistance
            if float(c.iloc[-1]) > line_last and float(c.iloc[-2]) <= (m * (x_last - 1) + b):
                signals.append({\"type\": \"BUY\", \"kind\": \"BREAKOUT_RES\", \"reason\": \"اختراق ترند مقاومة\"})

            # retest: price touches line after breakout (rough)
            if float(l.iloc[-1]) <= line_last <= float(h.iloc[-1]):
                signals.append({\"type\": \"INFO\", \"kind\": \"RETEST_RES\", \"reason\": \"لمس/إعادة اختبار قرب ترند المقاومة\"})

    # support trendline from last two pivot lows
    if len(lows) >= 2:
        i1, i2 = int(lows[-2]), int(lows[-1])
        y1, y2 = float(l.iloc[i1]), float(l.iloc[i2])
        if i2 != i1:
            m = (y2 - y1) / (i2 - i1)
            b = y2 - m * i2
            x_last = len(c) - 1
            line_last = m * x_last + b
            features["sup_tl"] = _safe_float(line_last)
            evidence.append(f\"ترند دعم من قيعان pivots (ميل={m:.4f})\")

            # breakdown: close crosses below support
            if float(c.iloc[-1]) < line_last and float(c.iloc[-2]) >= (m * (x_last - 1) + b):
                signals.append({\"type\": \"SELL\", \"kind\": \"BREAKDOWN_SUP\", \"reason\": \"كسر ترند دعم\"})

            # retest: price touches line
            if float(l.iloc[-1]) <= line_last <= float(h.iloc[-1]):
                signals.append({\"type\": \"INFO\", \"kind\": \"RETEST_SUP\", \"reason\": \"لمس/إعادة اختبار قرب ترند الدعم\"})

    if not features:
        evidence.append(\"لم يتم العثور على pivots كافية لبناء ترندلاين دعم/مقاومة.\")
        conf = 30
    else:
        conf = 60

    # mild boost if multiple signals
    conf += min(15, 5 * len(signals))
    conf = int(max(0, min(100, conf)))

    return {
        \"name\": \"Trendline Breakout\",
        \"features\": features,
        \"signals\": signals,
        \"evidence\": evidence,
        \"confidence\": conf,
        \"errors\": [],
    }


# ----------------------------
# Pack Builder
# ----------------------------

def compute_advanced_technical_pack(
    df: pd.DataFrame,
    symbol: str = \"\",
    timeframe: str = \"1d\",
) -> Dict[str, Any]:
    \"\"\"Compute a compact pack of advanced indicators.\n\n    Returns a dict with named sub-results.\n    \"\"\"\n    out: Dict[str, Any] = {\n        \"meta\": {\n            \"symbol\": symbol,\n            \"timeframe\": timeframe,\n            \"rows\": int(len(df)) if df is not None else 0,\n        }\n    }\n\n    out[\"rls_forecast\"] = rls_forecast(df)\n    out[\"chaos_wrsi\"] = chaos_weighted_rsi(df)\n    out[\"volume_profile_clusters\"] = volume_profile_clusters(df)\n    out[\"trendline_breakout\"] = trendline_breakout(df)\n\n    return out\n```

---

```python
# ai_engine_core/packs.py
# -*- coding: utf-8 -*-

\"\"\"AI Engine Packs.\n\nهذا الملف يوفّر Builders لحزم البيانات (Features) التي يعتمد عليها المستشار.\n\nملاحظة مهمة:\n- تم إنشاؤه/إضافته لأن reporting.py كان يتوقع وجوده (Missing pack builders).\n- لا يحذف أي منطق سابق؛ بل يضيف طبقة تجميع منظمة.\n\"\"\"\n\nfrom __future__ import annotations\n\nfrom typing import Any, Dict, Optional\n\nimport numpy as np\nimport pandas as pd\n\n# Optional advanced pack\ntry:\n    from technical_indicators.advanced import compute_advanced_technical_pack\nexcept Exception:\n    compute_advanced_technical_pack = None\n\n\ndef _safe_float(x: Any, default: float = 0.0) -> float:\n    try:\n        if x is None:\n            return default\n        return float(x)\n    except Exception:\n        return default\n\n\ndef _ensure_ohlcv(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:\n    if df is None or not isinstance(df, pd.DataFrame) or df.empty:\n        return None\n    # Normalize columns\n    cols = {c.lower(): c for c in df.columns}\n    # common yfinance names already ok\n    return df\n\n\ndef build_technical_pack(\n    df_price: Optional[pd.DataFrame],\n    symbol: str = \"\",\n    timeframe: str = \"1d\",\n) -> Dict[str, Any]:\n    \"\"\"Build technical pack (baseline + advanced).\n\n    - baseline: returns basic stats (last close, return, volatility)\n    - advanced: optional indicators via technical_indicators.advanced\n    \"\"\"\n    df = _ensure_ohlcv(df_price)\n\n    pack: Dict[str, Any] = {\n        \"name\": \"technical\",\n        \"meta\": {\"symbol\": symbol, \"timeframe\": timeframe},\n        \"features\": {},\n        \"advanced\": {},\n        \"errors\": [],\n    }\n\n    if df is None or df.empty:\n        pack[\"errors\"].append(\"missing_price_data\")\n        return pack\n\n    close = None\n    for c in [\"Close\", \"close\", \"CLOSE\"]:\n        if c in df.columns:\n            close = df[c].astype(float)\n            break\n    if close is None:\n        pack[\"errors\"].append(\"missing_close\")\n        return pack\n\n    # Baseline features\n    ret = close.pct_change().fillna(0.0)\n    vol = ret.rolling(20).std().fillna(0.0)\n\n    pack[\"features\"].update(\n        {\n            \"close\": _safe_float(close.iloc[-1]),\n            \"ret_1d\": _safe_float(ret.iloc[-1]),\n            \"vol_20\": _safe_float(vol.iloc[-1]),\n            \"trend_20\": _safe_float(close.iloc[-1] - close.iloc[-20]) if len(close) >= 20 else 0.0,\n        }\n    )\n\n    # Advanced features pack (optional)\n    if compute_advanced_technical_pack is not None:\n        try:\n            adv = compute_advanced_technical_pack(df, symbol=symbol, timeframe=timeframe)\n            pack[\"advanced\"] = adv\n\n            # Flatten some useful features into top-level for the AI report\n            rls = adv.get(\"rls_forecast\", {}).get(\"features\", {})\n            wrsi = adv.get(\"chaos_wrsi\", {}).get(\"features\", {})\n            vp = adv.get(\"volume_profile_clusters\", {}).get(\"features\", {})\n            tl = adv.get(\"trendline_breakout\", {}).get(\"features\", {})\n\n            # minimal flatten\n            for k, v in {\n                \"rls_slope\": rls.get(\"rls_slope\"),\n                \"rls_band_width\": rls.get(\"band_width\"),\n                \"wrsi\": wrsi.get(\"wrsi\"),\n                \"wrsi_chaos\": wrsi.get(\"chaos\"),\n                \"vp_main_poc\": vp.get(\"main_poc\"),\n                \"tl_res\": tl.get(\"res_tl\"),\n                \"tl_sup\": tl.get(\"sup_tl\"),\n            }.items():\n                if v is None:\n                    continue\n                pack[\"features\"][k] = _safe_float(v)\n\n        except Exception as e:\n            pack[\"errors\"].append(f\"advanced_pack_error: {e}\")\n\n    return pack\n\n\ndef build_vsa_pack(\n    df_price: Optional[pd.DataFrame],\n    symbol: str = \"\",\n    timeframe: str = \"1d\",\n) -> Dict[str, Any]:\n    \"\"\"Placeholder VSA pack.\n\n    ملاحظة: هذا pack موجود لتجنب خطأ Missing pack builders.\n    تستطيع لاحقًا توسيعه وربطه بمحركات VSA داخل مشروعك.\n    \"\"\"\n    df = _ensure_ohlcv(df_price)\n    pack: Dict[str, Any] = {\n        \"name\": \"vsa\",\n        \"meta\": {\"symbol\": symbol, \"timeframe\": timeframe},\n        \"features\": {},\n        \"errors\": [],\n    }\n\n    if df is None or df.empty:\n        pack[\"errors\"].append(\"missing_price_data\")\n        return pack\n\n    vol = None\n    for c in [\"Volume\", \"volume\", \"VOL\"]:\n        if c in df.columns:\n            vol = df[c].astype(float)\n            break\n\n    if vol is None:\n        pack[\"errors\"].append(\"missing_volume\")\n        return pack\n\n    pack[\"features\"].update(\n        {\n            \"volume_last\": _safe_float(vol.iloc[-1]),\n            \"volume_avg20\": _safe_float(vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else _safe_float(vol.mean()),\n        }\n    )\n\n    return pack\n\n\ndef build_fundamental_pack(\n    fundamentals: Optional[Dict[str, Any]] = None,\n    symbol: str = \"\",\n) -> Dict[str, Any]:\n    \"\"\"Fundamental pack (lightweight).\n\n    - لا يجبر التطبيق على وجود بيانات مالية كاملة.\n    - يُستخدم كحاوية موحدة للمستشار.\n    \"\"\"\n    pack: Dict[str, Any] = {\n        \"name\": \"fundamental\",\n        \"meta\": {\"symbol\": symbol},\n        \"features\": {},\n        \"errors\": [],\n    }\n\n    if not fundamentals or not isinstance(fundamentals, dict):\n        pack[\"errors\"].append(\"missing_fundamentals\")\n        return pack\n\n    # Pass-through a few common keys if present\n    for k in [\n        \"revenue\",\n        \"net_income\",\n        \"total_assets\",\n        \"total_liabilities\",\n        \"equity\",\n        \"operating_cash_flow\",\n        \"free_cash_flow\",\n        \"eps\",\n    ]:\n        if k in fundamentals and fundamentals[k] is not None:\n            pack[\"features\"][k] = _safe_float(fundamentals[k])\n\n    return pack\n```

---

### ✅ بخصوص سؤالك “تبغاها تظهر في أي تبويب؟”
أنا حطّيتها (افتراضيًا) هنا:
- داخل **📈 التحليل الفني** → تبويب فرعي جديد باسم **“مؤشرات متقدمة”** (بدون ما نضيف تبويب رئيسي جديد)

إذا تبغاها بدل كذا (مثلاً: **تبويب رئيسي مستقل داخل analysis/__init__.py**) قلّي بس:  
**هل تبغاها تبويب رئيسي جديد اسمه “🚀 مؤشرات متقدمة”؟**  
وأطبّقها مباشرة بدون ما ألمس باقي التبويبات إلا بالإضافة فقط.
