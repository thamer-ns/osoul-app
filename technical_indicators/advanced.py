#technical_indicators/advanced.py
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _get_series(df: pd.DataFrame, name: str) -> Optional[pd.Series]:
    if name in df.columns:
        s = df[name]
        if isinstance(s, pd.Series):
            return s
        return pd.Series(s)
    return None


def _safe_float(x: object) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        return None
    return None


def _ema(series: pd.Series, span: int) -> pd.Series:
    # span>0; adjust=False for standard trading EMA
    return series.ewm(span=max(2, int(span)), adjust=False, min_periods=max(2, int(span))).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    length = max(2, int(length))
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / (avg_loss.replace(0.0, np.nan))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def rls_forecast(
    df: pd.DataFrame,
    price_col: str = "Close",
    lam: float = 0.99,
    band_mult: float = 2.0,
) -> Dict:
    """Recursive Least Squares forecast of price as a line over time.

    Model: y = w1 + w2 * t, updated online with RLS.

    Returns a schema dict containing mean line, bands, and mean-reversion style signals.
    """
    close = _get_series(df, price_col)
    high = _get_series(df, "High") or close
    low = _get_series(df, "Low") or close

    if close is None or len(close) < 40:
        return {
            "name": "rls_forecast",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": ["insufficient_data"],
        }

    lam = float(lam)
    lam = 0.90 if lam < 0.90 else (0.999 if lam > 0.999 else lam)
    band_mult = float(band_mult)

    y = close.astype(float).to_numpy()
    n = len(y)

    # RLS state
    w = np.array([y[0], 0.0], dtype=float)  # intercept, slope
    P = np.eye(2, dtype=float) * 1e3
    msqe = 0.0
    mean = np.zeros(n, dtype=float)
    upper = np.zeros(n, dtype=float)
    lower = np.zeros(n, dtype=float)
    slope = np.zeros(n, dtype=float)
    stds = np.zeros(n, dtype=float)

    overbought = False
    oversold = False
    signals: List[dict] = []

    for i in range(n):
        x = np.array([1.0, float(i)], dtype=float)
        yhat = float(x @ w)
        e = float(y[i] - yhat)

        # Kalman gain
        denom = lam + float(x.T @ P @ x)
        k = (P @ x) / denom
        w = w + k * e
        P = (P - np.outer(k, x.T @ P)) / lam

        # Uncertainty estimate (EWMA of squared error)
        msqe = lam * msqe + (1.0 - lam) * (e * e)
        std = math.sqrt(msqe) if msqe > 0 else 0.0

        mean[i] = yhat
        stds[i] = std
        upper[i] = yhat + band_mult * std
        lower[i] = yhat - band_mult * std
        slope[i] = float(w[1])

        # Mean reversion style flags
        if i > 0:
            if float(high.iloc[i]) > upper[i]:
                overbought = True
            if float(low.iloc[i]) < lower[i]:
                oversold = True

            # Sell when price re-enters from upper
            if overbought and float(close.iloc[i]) < upper[i] and float(close.iloc[i - 1]) >= upper[i - 1]:
                signals.append({"type": "sell", "index": int(i), "reason": "rls_reenter_from_upper"})
                overbought = False

            # Buy when price re-enters from lower
            if oversold and float(close.iloc[i]) > lower[i] and float(close.iloc[i - 1]) <= lower[i - 1]:
                signals.append({"type": "buy", "index": int(i), "reason": "rls_reenter_from_lower"})
                oversold = False

    # Latest features
    last = n - 1
    slope_now = _safe_float(slope[last])
    std_now = _safe_float(stds[last])
    width_pct = None
    if std_now is not None and _safe_float(mean[last]) and float(mean[last]) != 0:
        width_pct = 100.0 * (2.0 * band_mult * std_now) / float(mean[last])

    evidence: List[str] = []
    conf = 0
    if slope_now is not None:
        if slope_now > 0:
            evidence.append("اتجاه RLS يميل للصعود (ميل موجب).")
            conf += 10
        elif slope_now < 0:
            evidence.append("اتجاه RLS يميل للهبوط (ميل سالب).")
            conf += 10

    if width_pct is not None:
        if width_pct < 4:
            evidence.append("نطاق عدم اليقين في RLS ضيق نسبيًا (تذبذب منخفض).")
            conf += 10
        elif width_pct > 10:
            evidence.append("نطاق عدم اليقين في RLS واسع (تذبذب مرتفع) — خفف المخاطرة.")
            conf += 5

    # Include last signal if recent
    if signals:
        s = signals[-1]
        if last - int(s.get("index", last)) <= 5:
            evidence.append("ظهرت إشارة ارتداد للمتوسط (RLS) مؤخرًا.")
            conf += 10

    conf = max(0, min(60, conf))

    return {
        "name": "rls_forecast",
        "features": {
            "rls_slope": slope_now,
            "rls_band_width_pct": _safe_float(width_pct),
            "rls_std": std_now,
            "rls_close_minus_mean": _safe_float(float(close.iloc[last]) - mean[last]),
        },
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": [],
        "series": {
            "rls_mean": mean,
            "rls_upper": upper,
            "rls_lower": lower,
        },
    }


def chaos_weighted_rsi(
    df: pd.DataFrame,
    price_col: str = "Close",
    rsi_len: int = 14,
    chaos_len: int = 20,
) -> Dict:
    """Chaos-Weighted RSI.

    الفكرة: نُقدّر "chaos" كمؤشر لتغير النظام (trend/range) عبر نسبة
    التذبذب العشوائي إلى الاتجاه (مقياس بسيط)، ثم نجعل التنعيم/الاستجابة
    ديناميكية: كلما زاد chaos → نعطي وزنًا أكبر للحركة الحديثة.
    """
    close = _get_series(df, price_col)
    if close is None or len(close) < max(rsi_len, chaos_len) * 3:
        return {
            "name": "chaos_wrsi",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": ["insufficient_data"],
        }

    close = close.astype(float)
    base_rsi = _rsi(close, rsi_len)

    # Chaos proxy: (sum |ret|) / |sum ret| in window -> higher means more choppy
    ret = close.pct_change().fillna(0.0)
    abs_sum = ret.abs().rolling(chaos_len, min_periods=chaos_len).sum()
    net_sum = ret.rolling(chaos_len, min_periods=chaos_len).sum().abs()
    chaos = (abs_sum / (net_sum.replace(0.0, np.nan))).clip(lower=1.0, upper=10.0)
    # Normalize to 0..1
    chaos_n = ((chaos - 1.0) / 9.0).clip(0.0, 1.0).fillna(0.0)

    # Dynamic smoothing: alpha in [0.05..0.3]
    alpha = 0.05 + 0.25 * chaos_n
    wrsi = pd.Series(index=base_rsi.index, dtype=float)
    prev = None
    for i, v in enumerate(base_rsi.to_numpy()):
        a = float(alpha.iloc[i]) if i < len(alpha) else 0.1
        if prev is None or not math.isfinite(prev) or not math.isfinite(float(v)):
            prev = float(v) if math.isfinite(float(v)) else np.nan
        else:
            prev = prev + a * (float(v) - prev)
        wrsi.iloc[i] = prev

    # Simple divergence detection (pivot based)
    # We'll detect last 2 pivots in price and wrsi and see if divergence exists.
    def _pivots(s: pd.Series, left: int = 3, right: int = 3) -> Tuple[List[int], List[int]]:
        arr = s.to_numpy(dtype=float)
        highs: List[int] = []
        lows: List[int] = []
        for i in range(left, len(arr) - right):
            window = arr[i - left : i + right + 1]
            if not np.isfinite(arr[i]):
                continue
            if arr[i] == np.nanmax(window):
                highs.append(i)
            if arr[i] == np.nanmin(window):
                lows.append(i)
        return highs, lows

    ph, pl = _pivots(close, 3, 3)
    rh, rl = _pivots(wrsi.fillna(method="ffill"), 3, 3)

    signals: List[dict] = []
    evidence: List[str] = []
    conf = 0

    # Latest momentum state
    last = len(close) - 1
    wrsi_last = _safe_float(wrsi.iloc[last])
    chaos_last = _safe_float(chaos_n.iloc[last])

    if wrsi_last is not None:
        if wrsi_last >= 70:
            evidence.append("Chaos-WRSI في منطقة تشبع شرائي (>70).")
            conf += 10
        elif wrsi_last <= 30:
            evidence.append("Chaos-WRSI في منطقة تشبع بيعي (<30).")
            conf += 10
        elif wrsi_last >= 50:
            evidence.append("Chaos-WRSI أعلى 50 (زخم إيجابي).")
            conf += 6
        else:
            evidence.append("Chaos-WRSI أسفل 50 (زخم سلبي).")
            conf += 6

    if chaos_last is not None:
        if chaos_last >= 0.7:
            evidence.append("السوق متذبذب/متقطع نسبيًا (chaos مرتفع) — إشارات التذبذب أكثر من الاتجاه.")
            conf += 6
        elif chaos_last <= 0.3:
            evidence.append("السوق أكثر انتظامًا (chaos منخفض) — إشارات الاتجاه أكثر موثوقية.")
            conf += 6

    # Divergence (last two pivots)
    def _last2(ix: List[int]) -> Optional[Tuple[int, int]]:
        if len(ix) >= 2:
            return ix[-2], ix[-1]
        return None

    p2l = _last2(pl)
    r2l = _last2(rl)
    if p2l and r2l:
        p_a, p_b = p2l
        r_a, r_b = r2l
        if abs(p_b - r_b) <= 8:  # roughly aligned
            if close.iloc[p_b] < close.iloc[p_a] and wrsi.iloc[r_b] > wrsi.iloc[r_a]:
                signals.append({"type": "bull_div", "index": int(last), "reason": "price_ll_wrsi_hl"})
                evidence.append("انحراف إيجابي: السعر صنع قاعًا أدنى بينما WRSI صنع قاعًا أعلى.")
                conf += 12

    p2h = _last2(ph)
    r2h = _last2(rh)
    if p2h and r2h:
        p_a, p_b = p2h
        r_a, r_b = r2h
        if abs(p_b - r_b) <= 8:
            if close.iloc[p_b] > close.iloc[p_a] and wrsi.iloc[r_b] < wrsi.iloc[r_a]:
                signals.append({"type": "bear_div", "index": int(last), "reason": "price_hh_wrsi_lh"})
                evidence.append("انحراف سلبي: السعر صنع قمة أعلى بينما WRSI صنع قمة أدنى.")
                conf += 12

    conf = max(0, min(55, conf))

    return {
        "name": "chaos_wrsi",
        "features": {
            "wrsi": wrsi_last,
            "chaos": chaos_last,
        },
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": [],
        "series": {
            "wrsi": wrsi.to_numpy(dtype=float),
            "chaos": chaos_n.to_numpy(dtype=float),
        },
    }


def _simple_kmeans_1d(x: np.ndarray, k: int, iters: int = 25, seed: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    """Very small 1D k-means (no sklearn).

    Returns (centroids, labels).
    """
    rng = np.random.default_rng(seed)
    x = x[np.isfinite(x)]
    if len(x) < k:
        # fallback: unique centroids
        centroids = np.unique(x)
        labels = np.zeros(len(x), dtype=int)
        return centroids, labels

    centroids = np.quantile(x, np.linspace(0.1, 0.9, k)).astype(float)
    for _ in range(iters):
        # assign
        d = np.abs(x[:, None] - centroids[None, :])
        labels = np.argmin(d, axis=1)
        new_centroids = np.array(
            [np.mean(x[labels == i]) if np.any(labels == i) else centroids[i] for i in range(k)],
            dtype=float,
        )
        if np.allclose(new_centroids, centroids, atol=1e-6, rtol=0):
            centroids = new_centroids
            break
        centroids = new_centroids

    # final labels on full x
    d = np.abs(x[:, None] - centroids[None, :])
    labels = np.argmin(d, axis=1)
    return centroids, labels


def volume_profile_clusters(
    df: pd.DataFrame,
    k: int = 8,
    lookback: int = 160,
) -> Dict:
    """Clustered volume profile using simple 1D k-means on typical price.

    Outputs per-cluster POC (volume-weighted price) and relative dominance.
    """
    close = _get_series(df, "Close")
    high = _get_series(df, "High")
    low = _get_series(df, "Low")
    volume = _get_series(df, "Volume")

    if close is None or volume is None or len(close) < max(60, lookback // 2):
        return {
            "name": "cluster_volume_profile",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": ["insufficient_data"],
        }

    n = len(close)
    lb = min(int(lookback), n)
    sl = slice(n - lb, n)
    c = close.iloc[sl].astype(float)
    h = (high.iloc[sl].astype(float) if high is not None else c)
    l = (low.iloc[sl].astype(float) if low is not None else c)
    v = volume.iloc[sl].astype(float).clip(lower=0.0)

    typ = (h + l + c) / 3.0
    x = typ.to_numpy(dtype=float)

    k = int(k)
    k = 4 if k < 4 else (12 if k > 12 else k)

    centroids, labels = _simple_kmeans_1d(x, k)

    # Map each point to cluster & compute volume stats
    # Because we k-means'ed on filtered x, we need labels length == len(x)
    if len(labels) != len(x):
        labels = np.zeros(len(x), dtype=int)

    poc_by_cluster: Dict[int, float] = {}
    vol_by_cluster: Dict[int, float] = {}

    for i in range(k):
        mask = labels == i
        if not np.any(mask):
            continue
        vol = float(np.nansum(v.to_numpy(dtype=float)[mask]))
        vol_by_cluster[i] = vol
        wprice = float(np.nansum(x[mask] * v.to_numpy(dtype=float)[mask]))
        poc_by_cluster[i] = wprice / vol if vol > 0 else float(centroids[i])

    total_vol = float(np.nansum(v))
    # pick dominant cluster
    dominant = max(vol_by_cluster.items(), key=lambda kv: kv[1])[0] if vol_by_cluster else 0
    dominant_poc = poc_by_cluster.get(dominant, float(np.nanmean(x)))

    close_last = float(close.iloc[-1])
    dom_share = vol_by_cluster.get(dominant, 0.0) / total_vol if total_vol > 0 else 0.0

    evidence: List[str] = []
    conf = 0

    if math.isfinite(dominant_poc):
        if close_last >= dominant_poc:
            evidence.append("السعر أعلى من منطقة POC المسيطرة (حجم متجمع) — دعم محتمل.")
            conf += 10
        else:
            evidence.append("السعر أسفل منطقة POC المسيطرة — مقاومة/تصريف محتمل.")
            conf += 10

    if dom_share >= 0.25:
        evidence.append("هناك تركّز حجم واضح في نطاق سعري محدد (تجميع/تصريف قوي).")
        conf += 8

    signals: List[dict] = []
    # Simple signal: cross dominant POC
    if lb >= 3:
        prev_close = float(close.iloc[-2])
        if prev_close < dominant_poc <= close_last:
            signals.append({"type": "poc_cross_up", "index": int(len(df) - 1), "reason": "cross_above_dominant_poc"})
        if prev_close > dominant_poc >= close_last:
            signals.append({"type": "poc_cross_down", "index": int(len(df) - 1), "reason": "cross_below_dominant_poc"})

    conf = max(0, min(50, conf))

    return {
        "name": "cluster_volume_profile",
        "features": {
            "dom_poc": _safe_float(dominant_poc),
            "dom_poc_share": _safe_float(dom_share),
            "close_vs_dom_poc": _safe_float(close_last - dominant_poc),
        },
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": [],
        "clusters": {
            "centroids": [float(c) for c in np.sort(centroids)],
            "dominant_cluster": int(dominant),
        },
    }


def trendline_breakout(
    df: pd.DataFrame,
    left: int = 3,
    right: int = 3,
    lookback: int = 200,
) -> Dict:
    """Auto trendline breakout (lightweight).

    - Detect pivot highs/lows
    - Fit a line through last two pivot highs (downtrend line) and last two pivot lows (uptrend line)
    - Report breakout if close crosses the line.

    This is a simplified version suitable for a baseline implementation.
    """
    close = _get_series(df, "Close")
    high = _get_series(df, "High") or close
    low = _get_series(df, "Low") or close

    if close is None or len(close) < 80:
        return {
            "name": "trendline_breakout",
            "features": {},
            "signals": [],
            "evidence": [],
            "confidence": 0,
            "errors": ["insufficient_data"],
        }

    n = len(close)
    lb = min(int(lookback), n)
    start = n - lb

    h = high.iloc[start:].astype(float).to_numpy()
    l = low.iloc[start:].astype(float).to_numpy()
    c = close.iloc[start:].astype(float).to_numpy()

    def pivots(arr: np.ndarray, left_: int, right_: int) -> Tuple[List[int], List[int]]:
        ph: List[int] = []
        pl: List[int] = []
        for i in range(left_, len(arr) - right_):
            window = arr[i - left_ : i + right_ + 1]
            if arr[i] == np.nanmax(window):
                ph.append(i)
            if arr[i] == np.nanmin(window):
                pl.append(i)
        return ph, pl

    ph, pl = pivots(c, max(2, left), max(2, right))

    def last2(ix: List[int]) -> Optional[Tuple[int, int]]:
        return (ix[-2], ix[-1]) if len(ix) >= 2 else None

    evidence: List[str] = []
    signals: List[dict] = []
    features: Dict[str, Optional[float]] = {}
    conf = 0

    # Downtrend line from last two pivot highs (use close pivots)
    t2h = last2(ph)
    if t2h:
        a, b = t2h
        if b != a:
            m = (c[b] - c[a]) / float(b - a)
            y0 = c[a] - m * a
            # value at last bar
            tl_last = m * (lb - 1) + y0
            features["down_tl_slope"] = _safe_float(m)
            features["down_tl_value"] = _safe_float(tl_last)
            if c[-2] <= (m * (lb - 2) + y0) and c[-1] > tl_last:
                signals.append({"type": "breakout_up", "index": int(n - 1), "reason": "close_crossed_downtrend"})
                evidence.append("كسر ترند هابط (Trendline) بإغلاق فوق الخط.")
                conf += 12

    # Uptrend line from last two pivot lows
    t2l = last2(pl)
    if t2l:
        a, b = t2l
        if b != a:
            m = (c[b] - c[a]) / float(b - a)
            y0 = c[a] - m * a
            tl_last = m * (lb - 1) + y0
            features["up_tl_slope"] = _safe_float(m)
            features["up_tl_value"] = _safe_float(tl_last)
            if c[-2] >= (m * (lb - 2) + y0) and c[-1] < tl_last:
                signals.append({"type": "breakout_down", "index": int(n - 1), "reason": "close_crossed_uptrend"})
                evidence.append("كسر ترند صاعد (Trendline) بإغلاق أسفل الخط.")
                conf += 12

    if not evidence:
        evidence.append("لا يوجد كسر واضح للترندلاين تلقائيًا ضمن آخر البيانات.")
        conf += 4

    conf = max(0, min(45, conf))

    return {
        "name": "trendline_breakout",
        "features": features,
        "signals": signals,
        "evidence": evidence,
        "confidence": conf,
        "errors": [],
    }


def compute_advanced_technical_pack(df: pd.DataFrame) -> Dict:
    """Compute a small pack of advanced technical indicators.

    This function is designed to be called from ai_engine_core/packs.py.
    """
    results = []
    results.append(rls_forecast(df))
    results.append(chaos_weighted_rsi(df))
    results.append(volume_profile_clusters(df))
    results.append(trendline_breakout(df))

    # Merge features, collect evidence and compute combined score/confidence.
    features: Dict[str, Optional[float]] = {}
    evidence: List[str] = []
    signals: List[dict] = []
    conf_sum = 0
    conf_cnt = 0
    errors: List[str] = []

    for r in results:
        for k, v in (r.get("features") or {}).items():
            features[f"adv_{k}"] = v
        for e in (r.get("evidence") or []):
            evidence.append(e)
        for s in (r.get("signals") or []):
            signals.append({"indicator": r.get("name"), **s})
        c = _safe_float(r.get("confidence"))
        if c is not None:
            conf_sum += c
            conf_cnt += 1
        for er in (r.get("errors") or []):
            if er:
                errors.append(f"{r.get('name')}:{er}")

    confidence = int(round(conf_sum / conf_cnt)) if conf_cnt else 0

    # A lightweight score 0..25 based on confidence and signal presence
    score = 0
    if confidence >= 35:
        score += 8
    if any(s.get("type") in {"breakout_up", "bull_div", "poc_cross_up"} for s in signals):
        score += 9
    if any(s.get("type") in {"breakout_down", "bear_div", "poc_cross_down"} for s in signals):
        score -= 6

    score = max(-10, min(25, score))

    return {
        "name": "advanced_technical_pack",
        "score": int(score),
        "confidence": int(max(0, min(100, confidence))),
        "features": features,
        "signals": signals,
        "evidence": evidence,
        "errors": errors,
    }
