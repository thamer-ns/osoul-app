"""Confirmed-candle advanced indicators for Osoli v2.

The module deliberately separates signal direction (-100..100) from signal
confidence (0..100). Actionable events are emitted only from completed candles.
"""
from __future__ import annotations

import calendar
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

RIYADH_TZ = "Asia/Riyadh"
SAUDI_CLOSE_HOUR = 15
SAUDI_CLOSE_MINUTE = 20


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None or pd.isna(value) else float(value)
    except Exception:
        return default


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    for key in (name, name.lower(), name.upper(), name.capitalize()):
        if key in frame.columns:
            return pd.to_numeric(frame[key], errors="coerce")
    raise KeyError(f"Missing {name}")


def _bias(direction_score: float) -> str:
    if direction_score >= 20:
        return "bullish"
    if direction_score <= -20:
        return "bearish"
    return "neutral"


def _result(
    name: str,
    direction_score: float,
    confidence: float,
    summary: str,
    *,
    evidence: list[str] | None = None,
    signals: list[dict[str, Any]] | None = None,
    features: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> Dict[str, Any]:
    score = int(round(_clip(direction_score, -100, 100)))
    return {
        "name": name,
        "bias": _bias(score),
        "direction_score": score,
        "confidence": int(round(_clip(confidence, 0, 100))),
        "summary": summary,
        "evidence": evidence or [],
        "signals": signals or [],
        "features": features or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _intraday_delta(timeframe: str) -> pd.Timedelta | None:
    aliases = {
        "1m": "1min",
        "1min": "1min",
        "5m": "5min",
        "5min": "5min",
        "15m": "15min",
        "15min": "15min",
        "30m": "30min",
        "30min": "30min",
        "60m": "60min",
        "60min": "60min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
    }
    value = aliases.get(str(timeframe or "").lower(), str(timeframe or "").lower())
    try:
        if value.endswith("min"):
            return pd.Timedelta(minutes=int(value[:-3]))
        if value.endswith("h"):
            return pd.Timedelta(hours=int(value[:-1]))
    except (TypeError, ValueError):
        return None
    return None


def _to_riyadh(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize(RIYADH_TZ) if stamp.tzinfo is None else stamp.tz_convert(RIYADH_TZ)


def _market_close(day: pd.Timestamp) -> pd.Timestamp:
    normalized = day.tz_convert(RIYADH_TZ).normalize()
    return normalized + pd.Timedelta(hours=SAUDI_CLOSE_HOUR, minutes=SAUDI_CLOSE_MINUTE)


def _weekly_bucket_close(now: pd.Timestamp) -> pd.Timestamp:
    """Return the Thursday close ending the Saudi trading week containing now."""
    days_until_thursday = (3 - now.weekday()) % 7
    thursday = now.normalize() + pd.Timedelta(days=days_until_thursday)
    return _market_close(thursday)


def _monthly_bucket_close(now: pd.Timestamp) -> pd.Timestamp:
    """Approximate the final Saudi trading close of the calendar month.

    Official exchange holidays are provider-specific; this handles the stable
    Sunday-Thursday week and avoids treating a completed prior-month bar as live.
    """
    last_day_number = calendar.monthrange(now.year, now.month)[1]
    day = pd.Timestamp(year=now.year, month=now.month, day=last_day_number, tz=RIYADH_TZ)
    while day.weekday() in {4, 5}:
        day -= pd.Timedelta(days=1)
    return _market_close(day)


def is_live_bar(last_bar: Any, timeframe: str, now: Any | None = None) -> bool:
    """Determine whether the last bar is still forming in Riyadh market time."""
    current = _to_riyadh(now) if now is not None else pd.Timestamp.now(tz=RIYADH_TZ)
    last = _to_riyadh(last_bar)
    tf = str(timeframe or "1d").strip().lower()

    delta = _intraday_delta(tf)
    if delta is not None:
        return last + delta > current

    if tf in {"1d", "d", "day", "1day"}:
        return last.date() == current.date() and current < _market_close(current)

    if tf in {"1wk", "1w", "week", "weekly"}:
        bucket_close = _weekly_bucket_close(current)
        return last.normalize() == bucket_close.normalize() and current < bucket_close

    if tf in {"1mo", "1month", "month", "monthly"}:
        bucket_close = _monthly_bucket_close(current)
        return (last.year, last.month) == (current.year, current.month) and current < bucket_close

    return False


def confirmed_frame(frame: pd.DataFrame, timeframe: str) -> Tuple[pd.DataFrame, bool]:
    """Return only completed candles, preserving DataFrame metadata."""
    if frame is None or frame.empty:
        return pd.DataFrame(), False

    output = frame.copy().sort_index()
    attrs = dict(getattr(output, "attrs", {}) or {})
    parsed_index = pd.to_datetime(output.index, errors="coerce")
    valid = ~pd.isna(parsed_index)
    output = output.loc[valid].copy()
    output.index = parsed_index[valid]
    output.attrs.update(attrs)
    if output.empty:
        return output, False

    excluded = False
    try:
        if is_live_bar(output.index[-1], timeframe) and len(output) > 1:
            output = output.iloc[:-1].copy()
            output.attrs.update(attrs)
            excluded = True
    except Exception:
        if len(output) > 2:
            output = output.iloc[:-1].copy()
            output.attrs.update(attrs)
            excluded = True
    return output, excluded


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = gain.div(loss.replace(0, np.nan))
    return (100 - 100 / (1 + relative_strength)).fillna(50)


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high = _column(frame, "High")
    low = _column(frame, "Low")
    close = _column(frame, "Close")
    previous_close = close.shift()
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _pivots(series: pd.Series, left: int = 3, right: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(float)
    highs = np.zeros(len(values), dtype=bool)
    lows = np.zeros(len(values), dtype=bool)
    for index in range(left, len(values) - right):
        window = values[index - left : index + right + 1]
        if not np.isfinite(window).all():
            continue
        highs[index] = values[index] == window.max() and int((window == values[index]).sum()) == 1
        lows[index] = values[index] == window.min() and int((window == values[index]).sum()) == 1
    return highs, lows


def rls_forecast(frame: pd.DataFrame) -> Dict[str, Any]:
    if len(frame) < 40:
        return _result(
            "RLS Forecast",
            0,
            10,
            "بيانات غير كافية.",
            warnings=["يلزم 40 شمعة مغلقة."],
        )

    close = _column(frame, "Close").dropna()
    x_values = np.arange(len(close), dtype=float)
    log_close = np.log(close.to_numpy(float))
    weights = 0.985 ** (len(close) - 1 - x_values)
    design = np.column_stack([np.ones(len(x_values)), x_values])
    try:
        beta = np.linalg.solve(
            design.T @ (weights[:, None] * design),
            design.T @ (weights * log_close),
        )
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(design, log_close, rcond=None)[0]

    fitted = design @ beta
    residuals = log_close - fitted
    rmse = float(np.sqrt(np.average(residuals**2, weights=weights)))
    mean_price = float(np.exp(fitted[-1]))
    last_price = float(close.iloc[-1])
    slope_percent = float((np.exp(beta[1]) - 1) * 100)
    deviation = last_price / mean_price - 1 if mean_price > 0 else 0.0
    direction = _clip(slope_percent * 250 - deviation * 300, -100, 100)

    band = 1.7 * rmse
    upper_series = np.exp(fitted + band)
    lower_series = np.exp(fitted - band)
    upper = float(upper_series[-1])
    lower = float(lower_series[-1])
    signals: list[dict[str, Any]] = []
    if len(close) >= 2 and close.iloc[-2] < lower_series[-2] and last_price >= lower:
        signals.append(
            {
                "type": "BUY",
                "kind": "MEAN_REVERSION_CONFIRMED",
                "price": last_price,
                "confirmation": "closed_candle",
                "reason": "عاد الإغلاق داخل النطاق من الأسفل.",
            }
        )
    if len(close) >= 2 and close.iloc[-2] > upper_series[-2] and last_price <= upper:
        signals.append(
            {
                "type": "SELL",
                "kind": "MEAN_REVERSION_CONFIRMED",
                "price": last_price,
                "confirmation": "closed_candle",
                "reason": "عاد الإغلاق داخل النطاق من الأعلى.",
            }
        )

    summary = (
        "اتجاه تكيفي صاعد."
        if direction >= 20
        else "اتجاه تكيفي هابط."
        if direction <= -20
        else "اتجاه تكيفي محايد."
    )
    confidence = 55 + min(15, len(frame) / 15) - min(25, rmse * 500)
    return _result(
        "RLS Forecast",
        direction,
        confidence,
        summary,
        evidence=[
            f"الميل لكل شمعة {slope_percent:.3f}%",
            f"الانحراف عن المتوسط {deviation * 100:.2f}%",
        ],
        signals=signals,
        features={
            "close": last_price,
            "mean": mean_price,
            "upper": upper,
            "lower": lower,
            "slope_pct_per_bar": slope_percent,
            "rmse": rmse,
        },
    )


def chaos_weighted_rsi(frame: pd.DataFrame) -> Dict[str, Any]:
    if len(frame) < 50:
        return _result(
            "Chaos Weighted RSI",
            0,
            10,
            "بيانات غير كافية.",
            warnings=["يلزم 50 شمعة مغلقة."],
        )

    close = _column(frame, "Close").dropna()
    raw_rsi = _rsi(close)
    volatility = close.pct_change().rolling(30).std()
    low_quantile = volatility.rolling(120, min_periods=30).quantile(0.1)
    high_quantile = volatility.rolling(120, min_periods=30).quantile(0.9)
    chaos = (
        (volatility - low_quantile)
        .div((high_quantile - low_quantile).replace(0, np.nan))
        .clip(0, 1)
        .fillna(0.5)
    )
    spans = (3 + chaos * 8).round().astype(int)

    adaptive_values: list[float] = []
    previous_value = 50.0
    for rsi_value, span in zip(raw_rsi, spans):
        alpha = 2 / (int(span) + 1)
        previous_value = alpha * float(rsi_value) + (1 - alpha) * previous_value
        adaptive_values.append(previous_value)
    weighted_rsi = pd.Series(adaptive_values, index=raw_rsi.index)

    last_value = float(weighted_rsi.iloc[-1])
    prior_value = float(weighted_rsi.iloc[-2])
    direction = _clip((last_value - 50) * 2, -70, 70)
    signals: list[dict[str, Any]] = []
    if prior_value <= 30 < last_value:
        signals.append(
            {
                "type": "BUY",
                "kind": "OVERSOLD_EXIT_CONFIRMED",
                "value": last_value,
                "confirmation": "closed_candle",
                "reason": "خروج مؤكد من التشبع البيعي.",
            }
        )
    if prior_value >= 70 > last_value:
        signals.append(
            {
                "type": "SELL",
                "kind": "OVERBOUGHT_EXIT_CONFIRMED",
                "value": last_value,
                "confirmation": "closed_candle",
                "reason": "خروج مؤكد من التشبع الشرائي.",
            }
        )

    price_high_flags, price_low_flags = _pivots(close)
    lows = np.where(price_low_flags)[0]
    highs = np.where(price_high_flags)[0]
    if len(lows) >= 2:
        first, second = int(lows[-2]), int(lows[-1])
        if close.iloc[second] < close.iloc[first] and weighted_rsi.iloc[second] > weighted_rsi.iloc[first]:
            direction += 20
            signals.append(
                {
                    "type": "BUY",
                    "kind": "BULLISH_DIVERGENCE",
                    "confirmation": "closed_pivots",
                    "reason": "دايفرجنس إيجابي بين قاعين مؤكدين.",
                }
            )
    if len(highs) >= 2:
        first, second = int(highs[-2]), int(highs[-1])
        if close.iloc[second] > close.iloc[first] and weighted_rsi.iloc[second] < weighted_rsi.iloc[first]:
            direction -= 20
            signals.append(
                {
                    "type": "SELL",
                    "kind": "BEARISH_DIVERGENCE",
                    "confirmation": "closed_pivots",
                    "reason": "دايفرجنس سلبي بين قمتين مؤكدتين.",
                }
            )

    summary = (
        "الزخم إيجابي."
        if direction >= 20
        else "الزخم سلبي."
        if direction <= -20
        else "الزخم متوازن."
    )
    chaos_last = float(chaos.iloc[-1])
    return _result(
        "Chaos Weighted RSI",
        direction,
        55 + (1 - chaos_last) * 15,
        summary,
        evidence=[f"WRSI {last_value:.2f}", f"الاضطراب {chaos_last:.2f}"],
        signals=signals,
        features={
            "wrsi": last_value,
            "raw_rsi": float(raw_rsi.iloc[-1]),
            "chaos": chaos_last,
            "adaptive_span": int(spans.iloc[-1]),
        },
    )


def volume_profile_clusters(frame: pd.DataFrame, buckets: int = 16) -> Dict[str, Any]:
    if len(frame) < 60:
        return _result(
            "Volume Profile Clusters",
            0,
            10,
            "بيانات غير كافية.",
            warnings=["يلزم 60 شمعة مغلقة."],
        )

    high = _column(frame, "High")
    low = _column(frame, "Low")
    close = _column(frame, "Close")
    volume = _column(frame, "Volume").fillna(0)
    edges = np.linspace(float(low.min()), float(high.max()), max(6, int(buckets)) + 1)
    bucket_volume = np.zeros(len(edges) - 1)

    for candle_high, candle_low, candle_volume in zip(high, low, volume):
        touched = np.where((edges[:-1] <= candle_high) & (edges[1:] >= candle_low))[0]
        if len(touched) and np.isfinite(candle_volume) and candle_volume > 0:
            bucket_volume[touched] += float(candle_volume) / len(touched)

    total_volume = float(bucket_volume.sum())
    if total_volume <= 0:
        return _result(
            "Volume Profile Clusters",
            0,
            20,
            "الحجم غير متاح.",
            warnings=["بيانات الحجم صفرية."],
        )

    centers = (edges[:-1] + edges[1:]) / 2
    top_indices = np.argsort(bucket_volume)[::-1][:3]
    pocs = [float(centers[index]) for index in top_indices]
    last_price = float(close.iloc[-1])
    distance = last_price / pocs[0] - 1 if pocs[0] > 0 else 0.0
    direction = _clip(distance * 250, -45, 45)
    rows = [
        {
            "price_low": float(edges[index]),
            "price_high": float(edges[index + 1]),
            "poc": float(centers[index]),
            "volume": float(bucket_volume[index]),
            "volume_share": float(bucket_volume[index] / total_volume),
        }
        for index in range(len(bucket_volume))
    ]
    signals = []
    if abs(distance) <= 0.01:
        signals.append(
            {
                "type": "INFO",
                "kind": "NEAR_MAIN_POC",
                "poc": pocs[0],
                "reason": "السعر قريب من أكبر منطقة حجم.",
            }
        )
    summary = (
        "أعلى منطقة الحجم الرئيسة."
        if direction >= 20
        else "أسفل منطقة الحجم الرئيسة."
        if direction <= -20
        else "قريب من منطقة الحجم الرئيسة."
    )
    return _result(
        "Volume Profile Clusters",
        direction,
        60,
        summary,
        evidence=["المناطق الأقوى: " + "، ".join(f"{price:.2f}" for price in pocs)],
        signals=signals,
        features={
            "main_poc": pocs[0],
            "distance_from_poc_pct": distance * 100,
            "clusters": rows,
        },
    )


def trendline_breakout(frame: pd.DataFrame, lookback: int = 140) -> Dict[str, Any]:
    if len(frame) < 70:
        return _result(
            "Trendline Breakout",
            0,
            10,
            "بيانات غير كافية.",
            warnings=["يلزم 70 شمعة مغلقة."],
        )

    window = frame.tail(lookback)
    close = _column(window, "Close").reset_index(drop=True)
    high = _column(window, "High").reset_index(drop=True)
    low = _column(window, "Low").reset_index(drop=True)
    volume = _column(window, "Volume").fillna(0).reset_index(drop=True)
    atr = _atr(window).reset_index(drop=True)

    high_flags, _ = _pivots(high)
    _, low_flags = _pivots(low)
    high_indices = np.where(high_flags)[0]
    low_indices = np.where(low_flags)[0]
    features: dict[str, Any] = {}
    evidence: list[str] = []
    signals: list[dict[str, Any]] = []
    direction = 0.0
    current_index = len(close) - 1
    prior_index = current_index - 1
    atr_last = _number(atr.iloc[-1])
    volume_average = _number(volume.rolling(20).mean().iloc[-1], float(volume.iloc[-1]))
    volume_confirmed = float(volume.iloc[-1]) >= volume_average

    if len(high_indices) >= 2:
        first, second = int(high_indices[-2]), int(high_indices[-1])
        slope = (float(high.iloc[second]) - float(high.iloc[first])) / max(1, second - first)
        intercept = float(high.iloc[second]) - slope * second
        resistance_now = slope * current_index + intercept
        resistance_prior = slope * prior_index + intercept
        features["resistance_trendline"] = resistance_now
        evidence.append(f"ميل المقاومة {slope:.4f}")
        margin = float(close.iloc[-1]) - resistance_now
        if (
            close.iloc[-1] > resistance_now
            and close.iloc[-2] <= resistance_prior
            and (atr_last <= 0 or margin >= 0.15 * atr_last)
        ):
            direction += 75 if volume_confirmed else 65
            signals.append(
                {
                    "type": "BUY",
                    "kind": "BREAKOUT_RESISTANCE_CONFIRMED",
                    "price": float(close.iloc[-1]),
                    "trigger": float(resistance_now),
                    "confirmation": "closed_candle",
                    "reason": "إغلاق مؤكد أعلى المقاومة مع هامش ATR.",
                }
            )

    if len(low_indices) >= 2:
        first, second = int(low_indices[-2]), int(low_indices[-1])
        slope = (float(low.iloc[second]) - float(low.iloc[first])) / max(1, second - first)
        intercept = float(low.iloc[second]) - slope * second
        support_now = slope * current_index + intercept
        support_prior = slope * prior_index + intercept
        features["support_trendline"] = support_now
        evidence.append(f"ميل الدعم {slope:.4f}")
        margin = support_now - float(close.iloc[-1])
        if (
            close.iloc[-1] < support_now
            and close.iloc[-2] >= support_prior
            and (atr_last <= 0 or margin >= 0.15 * atr_last)
        ):
            direction -= 75 if volume_confirmed else 65
            signals.append(
                {
                    "type": "SELL",
                    "kind": "BREAKDOWN_SUPPORT_CONFIRMED",
                    "price": float(close.iloc[-1]),
                    "trigger": float(support_now),
                    "confirmation": "closed_candle",
                    "reason": "إغلاق مؤكد أسفل الدعم مع هامش ATR.",
                }
            )

    summary = (
        "اختراق صاعد مؤكد."
        if direction >= 20
        else "كسر هابط مؤكد."
        if direction <= -20
        else "لا يوجد اختراق أو كسر مؤكد."
    )
    features.update(
        {
            "atr14": atr_last,
            "volume": float(volume.iloc[-1]),
            "volume_ma20": volume_average,
            "volume_confirmed": volume_confirmed,
            "confirmation": "closed_candle",
        }
    )
    confidence = 65 if high_indices.size >= 2 or low_indices.size >= 2 else 25
    return _result(
        "Trendline Breakout",
        direction,
        confidence,
        summary,
        evidence=evidence,
        signals=signals,
        features=features,
    )


def compute_advanced_technical_pack(
    frame: pd.DataFrame,
    symbol: str = "",
    timeframe: str = "1d",
) -> Dict[str, Any]:
    confirmed, excluded = confirmed_frame(frame, timeframe)
    meta = {
        "symbol": str(symbol),
        "timeframe": str(timeframe),
        "input_rows": len(frame) if frame is not None else 0,
        "confirmed_rows": len(confirmed),
        "live_bar_excluded": excluded,
        "confirmation_rule": "closed_candle",
    }
    if confirmed.empty:
        return {
            "meta": meta,
            "bias": "neutral",
            "direction_score": 0,
            "confidence": 0,
            "summary": "لا توجد شموع مغلقة صالحة.",
            "features": {},
            "evidence": [],
            "signals": [],
            "warnings": ["لا توجد بيانات مؤكدة."],
            "errors": [],
        }

    results = {
        "rls_forecast": rls_forecast(confirmed),
        "chaos_wrsi": chaos_weighted_rsi(confirmed),
        "volume_profile_clusters": volume_profile_clusters(confirmed),
        "trendline_breakout": trendline_breakout(confirmed),
    }
    values = list(results.values())
    weights = [max(0.05, _number(item.get("confidence")) / 100) for item in values]
    direction = float(
        np.average(
            [_number(item.get("direction_score")) for item in values],
            weights=weights,
        )
    )
    dispersion = float(np.std([_number(item.get("direction_score")) for item in values]))
    confidence = _clip(
        float(np.average([_number(item.get("confidence")) for item in values], weights=weights))
        - min(25, dispersion / 3),
        0,
        100,
    )

    signals: list[dict[str, Any]] = []
    evidence: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    features: dict[str, Any] = {}
    for key, result in results.items():
        signals.extend(result.get("signals") or [])
        evidence.extend(
            f"{result.get('name', key)}: {item}"
            for item in (result.get("evidence") or [])
        )
        warnings.extend(result.get("warnings") or [])
        errors.extend(result.get("errors") or [])
        for feature_key, feature_value in (result.get("features") or {}).items():
            if isinstance(feature_value, (str, int, float, bool)) or feature_value is None:
                features[f"{key}.{feature_key}"] = feature_value

    pack_bias = _bias(direction)
    label = {
        "bullish": "إيجابي",
        "bearish": "سلبي",
        "neutral": "محايد/مختلط",
    }[pack_bias]
    return {
        "meta": meta,
        **results,
        "bias": pack_bias,
        "direction_score": int(round(direction)),
        "confidence": int(round(confidence)),
        "summary": f"الميل الفني المتقدم {label} اعتمادًا على الشموع المغلقة فقط.",
        "features": features,
        "evidence": evidence[:30],
        "signals": signals[:30],
        "warnings": list(dict.fromkeys(warnings)),
        "errors": list(dict.fromkeys(errors)),
    }
