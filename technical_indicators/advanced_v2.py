"""Advanced technical indicators v2 for Osoli.

The module returns a stable schema for both the Streamlit UI and the AI engine:
``bias`` describes direction, ``direction_score`` is signed (-100..100), and
``confidence`` measures evidence quality (0..100). All breakout signals require
a candle close; confirmed pivots exclude the unconfirmed right-hand bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

TIMEFRAME_BARS_PER_YEAR = {
    "1m": 252 * 390,
    "5m": 252 * 78,
    "15m": 252 * 26,
    "30m": 252 * 13,
    "1h": 252 * 6.5,
    "4h": 252 * 1.625,
    "1d": 252,
    "1wk": 52,
    "1w": 52,
    "1mo": 12,
}


def _sf(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else float(default)
    except Exception:
        return float(default)


def _clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    aliases = {str(c).lower(): c for c in out.columns}
    for target in ("Open", "High", "Low", "Close", "Volume"):
        if target not in out.columns and target.lower() in aliases:
            out[target] = out[aliases[target.lower()]]
    required = ["Open", "High", "Low", "Close"]
    if not all(c in out.columns for c in required):
        return pd.DataFrame()
    if "Volume" not in out.columns:
        out["Volume"] = 0.0
    for col in required + ["Volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=required)
    out = out[(out["High"] >= out["Low"]) & (out["Close"] > 0)]
    return out


def _bias(score: float) -> str:
    if score >= 15:
        return "bullish"
    if score <= -15:
        return "bearish"
    return "neutral"


def _result(
    *,
    name: str,
    score: float,
    confidence: float,
    summary: str,
    evidence: Iterable[str] = (),
    signals: Iterable[Dict[str, Any]] = (),
    features: Dict[str, Any] | None = None,
    errors: Iterable[str] = (),
    series: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    score = float(np.clip(score, -100, 100))
    confidence = float(np.clip(confidence, 0, 100))
    return {
        "name": name,
        "bias": _bias(score),
        "direction_score": round(score, 2),
        "confidence": round(confidence, 2),
        "summary": summary,
        "evidence": [str(x) for x in evidence if str(x).strip()],
        "signals": list(signals),
        "features": features or {},
        "errors": [str(x) for x in errors if str(x).strip()],
        "warnings": [],
        "series": series or {},
        "confirmation": "close",
    }


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    previous = close.shift(1)
    tr = pd.concat([(high - low), (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / max(1, period), adjust=False, min_periods=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def _confirmed_pivots(series: pd.Series, left: int = 3, right: int = 3, high: bool = True) -> List[int]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    indexes: list[int] = []
    for i in range(left, len(values) - right):
        center = values[i]
        if not np.isfinite(center):
            continue
        window = values[i - left : i + right + 1]
        if high:
            condition = center == np.nanmax(window) and np.sum(window == center) == 1
        else:
            condition = center == np.nanmin(window) and np.sum(window == center) == 1
        if condition:
            indexes.append(i)
    return indexes


def _linear_fit(points: List[Tuple[int, float]], x_now: int) -> Tuple[float, float, float]:
    if len(points) < 2:
        return np.nan, np.nan, np.nan
    x = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0
    return float(slope * x_now + intercept), float(slope), float(np.clip(r2, 0, 1))


def rls_forecast(df: pd.DataFrame, timeframe: str = "1d", lam: float = 0.995) -> Dict[str, Any]:
    data = _clean_ohlcv(df)
    if len(data) < 40:
        return _result(name="RLS Forecast v2", score=0, confidence=10, summary="البيانات غير كافية", errors=["يلزم 40 شمعة على الأقل"])

    close = data["Close"].astype(float)
    y = np.log(close.to_numpy())
    n = len(y)
    w = np.zeros(2, dtype=float)
    covariance = np.eye(2) * 1000.0
    fitted = np.full(n, np.nan)
    residual_variance = 0.0
    residual_std = np.full(n, np.nan)

    for i, target in enumerate(y):
        x = np.array([1.0, float(i)])
        denominator = lam + float(x @ covariance @ x)
        gain = covariance @ x / max(denominator, 1e-12)
        error = float(target - x @ w)
        w = w + gain * error
        covariance = (covariance - np.outer(gain, x @ covariance)) / lam
        fitted[i] = float(x @ w)
        residual_variance = lam * residual_variance + (1 - lam) * error * error
        residual_std[i] = np.sqrt(max(residual_variance, 0.0))

    mean_price = np.exp(fitted)
    upper = np.exp(fitted + 1.7 * residual_std)
    lower = np.exp(fitted - 1.7 * residual_std)
    last = float(close.iloc[-1])
    annual_factor = float(TIMEFRAME_BARS_PER_YEAR.get(str(timeframe).lower(), 252))
    annualised_slope = float(np.expm1(w[1] * annual_factor))
    position = (last - lower[-1]) / max(upper[-1] - lower[-1], 1e-12)

    trend_component = np.clip(annualised_slope * 120.0, -60, 60)
    location_component = np.clip((position - 0.5) * 35.0, -20, 20)
    score = float(trend_component + location_component)
    signals: list[dict] = []
    if close.iloc[-2] <= upper[-2] and close.iloc[-1] > upper[-1]:
        signals.append({"type": "BUY", "kind": "CLOSE_ABOVE_RLS_BAND", "price": last, "reason": "إغلاق أعلى نطاق RLS"})
        score += 15
    elif close.iloc[-2] >= lower[-2] and close.iloc[-1] < lower[-1]:
        signals.append({"type": "SELL", "kind": "CLOSE_BELOW_RLS_BAND", "price": last, "reason": "إغلاق أسفل نطاق RLS"})
        score -= 15

    band_pct = (upper[-1] - lower[-1]) / max(last, 1e-12)
    confidence = 45 + min(25, n / 10) + max(0, 20 - band_pct * 100)
    summary = "اتجاه RLS صاعد" if score > 15 else "اتجاه RLS هابط" if score < -15 else "RLS محايد أو متوازن"
    return _result(
        name="RLS Forecast v2",
        score=score,
        confidence=confidence,
        summary=summary,
        evidence=[f"الميل السنوي التقريبي: {annualised_slope * 100:.2f}%", f"موضع السعر داخل النطاق: {position * 100:.1f}%"],
        signals=signals,
        features={"rls_slope_annualised": annualised_slope, "mean": mean_price[-1], "upper": upper[-1], "lower": lower[-1], "band_width_pct": band_pct * 100},
        series={"rls_mean": mean_price.tolist(), "upper_band": upper.tolist(), "lower_band": lower.tolist()},
    )


def chaos_weighted_rsi(df: pd.DataFrame, timeframe: str = "1d", period: int = 14, chaos_window: int = 30) -> Dict[str, Any]:
    data = _clean_ohlcv(df)
    if len(data) < max(50, chaos_window + period):
        return _result(name="Chaos WRSI v2", score=0, confidence=10, summary="البيانات غير كافية", errors=["تاريخ سعري قصير"])

    close = data["Close"].astype(float)
    raw = _rsi(close, period)
    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rolling_vol = returns.rolling(chaos_window, min_periods=10).std().fillna(0.0)
    rank = rolling_vol.rolling(max(chaos_window * 4, 60), min_periods=20).rank(pct=True).fillna(0.5)
    spans = (2 + rank * 10).round().clip(2, 12).astype(int)

    weighted = np.full(len(raw), 50.0)
    previous = 50.0
    for i, value in enumerate(raw.to_numpy(dtype=float)):
        alpha = 2.0 / (int(spans.iloc[i]) + 1.0)
        previous = alpha * (value if np.isfinite(value) else previous) + (1 - alpha) * previous
        weighted[i] = previous

    wrsi = pd.Series(weighted, index=data.index)
    last = float(wrsi.iloc[-1])
    score = float(np.clip((last - 50) * 1.6, -55, 55))
    signals: list[dict] = []

    lows = _confirmed_pivots(close, 3, 3, high=False)
    highs = _confirmed_pivots(close, 3, 3, high=True)
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if close.iloc[b] < close.iloc[a] and wrsi.iloc[b] > wrsi.iloc[a]:
            signals.append({"type": "BUY", "kind": "BULLISH_DIVERGENCE", "index": b, "reason": "دايفرجنس إيجابي مؤكد"})
            score += 25
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if close.iloc[b] > close.iloc[a] and wrsi.iloc[b] < wrsi.iloc[a]:
            signals.append({"type": "SELL", "kind": "BEARISH_DIVERGENCE", "index": b, "reason": "دايفرجنس سلبي مؤكد"})
            score -= 25

    if last < 30:
        signals.append({"type": "INFO", "kind": "OVERSOLD", "value": last, "reason": "تشبع بيع؛ يحتاج تأكيد ارتداد"})
    elif last > 70:
        signals.append({"type": "INFO", "kind": "OVERBOUGHT", "value": last, "reason": "تشبع شراء؛ يحتاج تأكيد ضعف"})

    chaos = float(rank.iloc[-1])
    confidence = 55 + min(20, len(data) / 15) - chaos * 12
    summary = "زخم إيجابي" if score > 15 else "زخم سلبي" if score < -15 else "الزخم محايد"
    return _result(
        name="Chaos WRSI v2",
        score=score,
        confidence=confidence,
        summary=summary,
        evidence=[f"WRSI الحالي: {last:.2f}", f"رتبة التقلب: {chaos * 100:.1f}%"],
        signals=signals,
        features={"wrsi": last, "chaos_percentile": chaos, "is_overbought": last > 70, "is_oversold": last < 30},
        series={"wrsi": wrsi.tolist(), "chaos": rank.tolist()},
    )


@dataclass
class VolumeZone:
    low: float
    high: float
    volume: float

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


def volume_profile_clusters(df: pd.DataFrame, timeframe: str = "1d", bins: int = 24) -> Dict[str, Any]:
    data = _clean_ohlcv(df)
    if len(data) < 60:
        return _result(name="Volume Profile v2", score=0, confidence=10, summary="البيانات غير كافية", errors=["يلزم 60 شمعة على الأقل"])

    low_min = float(data["Low"].min())
    high_max = float(data["High"].max())
    if high_max <= low_min:
        return _result(name="Volume Profile v2", score=0, confidence=0, summary="النطاق السعري غير صالح")
    edges = np.linspace(low_min, high_max, bins + 1)
    volumes = np.zeros(bins, dtype=float)

    for _, row in data.iterrows():
        candle_low, candle_high = float(row["Low"]), float(row["High"])
        volume = max(0.0, _sf(row["Volume"]))
        first = int(np.clip(np.searchsorted(edges, candle_low, side="right") - 1, 0, bins - 1))
        last = int(np.clip(np.searchsorted(edges, candle_high, side="left"), first, bins - 1))
        touched = max(1, last - first + 1)
        volumes[first : last + 1] += volume / touched

    zones = [VolumeZone(float(edges[i]), float(edges[i + 1]), float(volumes[i])) for i in range(bins)]
    poc_index = int(np.argmax(volumes))
    poc = zones[poc_index].midpoint
    total = float(volumes.sum()) or 1.0

    ranked = np.argsort(volumes)[::-1]
    selected: list[int] = []
    accumulated = 0.0
    for index in ranked:
        selected.append(int(index))
        accumulated += float(volumes[index])
        if accumulated / total >= 0.70:
            break
    value_low = min(zones[i].low for i in selected)
    value_high = max(zones[i].high for i in selected)
    close = float(data["Close"].iloc[-1])
    atr_value = _sf(_atr(data).iloc[-1], close * 0.02)
    distance_atr = (close - poc) / max(atr_value, close * 0.005)
    score = float(np.clip(distance_atr * 18, -55, 55))
    signals = []
    if abs(close - poc) <= max(atr_value * 0.35, close * 0.005):
        signals.append({"type": "INFO", "kind": "NEAR_POC", "poc": poc, "reason": "السعر قريب من مركز الحجم"})
    summary = "السعر أعلى مركز الحجم" if score > 15 else "السعر أسفل مركز الحجم" if score < -15 else "السعر قريب من مركز التوازن"
    return _result(
        name="Volume Profile v2",
        score=score,
        confidence=55 + min(25, len(data) / 12),
        summary=summary,
        evidence=[f"POC: {poc:.2f}", f"منطقة القيمة 70%: {value_low:.2f} – {value_high:.2f}"],
        signals=signals,
        features={"main_poc": poc, "value_area_low": value_low, "value_area_high": value_high, "close": close, "distance_from_poc_atr": distance_atr},
        series={"clusters": [{"price_low": z.low, "price_high": z.high, "poc": z.midpoint, "volume": z.volume, "volume_share": z.volume / total} for z in zones]},
    )


def trendline_breakout(df: pd.DataFrame, timeframe: str = "1d", lookback: int = 160) -> Dict[str, Any]:
    data = _clean_ohlcv(df).tail(max(80, lookback)).copy()
    if len(data) < 70:
        return _result(name="Trendline Breakout v2", score=0, confidence=10, summary="البيانات غير كافية", errors=["يلزم 70 شمعة على الأقل"])

    close, high, low = data["Close"], data["High"], data["Low"]
    volume = data["Volume"]
    atr = _atr(data)
    atr_last = _sf(atr.iloc[-1], float(close.iloc[-1]) * 0.02)
    volume_avg = _sf(volume.rolling(20).mean().iloc[-1], 0.0)
    volume_ratio = _sf(volume.iloc[-1] / volume_avg, 1.0) if volume_avg > 0 else 1.0
    x_now = len(data) - 1

    high_pivots = _confirmed_pivots(high, 3, 3, high=True)[-5:]
    low_pivots = _confirmed_pivots(low, 3, 3, high=False)[-5:]
    resistance, resistance_slope, resistance_r2 = _linear_fit([(i, float(high.iloc[i])) for i in high_pivots], x_now)
    support, support_slope, support_r2 = _linear_fit([(i, float(low.iloc[i])) for i in low_pivots], x_now)

    score = 0.0
    signals: list[dict] = []
    current, previous = float(close.iloc[-1]), float(close.iloc[-2])
    buffer = max(atr_last * 0.10, current * 0.001)

    if np.isfinite(resistance):
        previous_resistance = resistance - resistance_slope
        if previous <= previous_resistance + buffer and current > resistance + buffer:
            confirmed = volume_ratio >= 1.10
            signals.append({"type": "BUY", "kind": "BREAKOUT_RESISTANCE", "price": current, "level": resistance, "volume_confirmed": confirmed, "reason": "اختراق مقاومة بإغلاق الشمعة"})
            score += 45 if confirmed else 30
        elif current > resistance:
            score += 18
    if np.isfinite(support):
        previous_support = support - support_slope
        if previous >= previous_support - buffer and current < support - buffer:
            confirmed = volume_ratio >= 1.10
            signals.append({"type": "SELL", "kind": "BREAKDOWN_SUPPORT", "price": current, "level": support, "volume_confirmed": confirmed, "reason": "كسر دعم بإغلاق الشمعة"})
            score -= 45 if confirmed else 30
        elif current < support:
            score -= 18

    trend_score = 0.0
    if np.isfinite(support_slope) and np.isfinite(resistance_slope):
        trend_score = np.clip(((support_slope + resistance_slope) / 2) / max(current, 1e-12) * 10000, -25, 25)
        score += trend_score

    fit_quality = np.nanmean([x for x in (resistance_r2, support_r2) if np.isfinite(x)])
    if not np.isfinite(fit_quality):
        fit_quality = 0.0
    confidence = 35 + fit_quality * 35 + min(15, len(data) / 12) + min(10, max(0, volume_ratio - 1) * 10)
    summary = "اختراق أو اتجاه صاعد" if score > 15 else "كسر أو اتجاه هابط" if score < -15 else "لا يوجد كسر مؤكد"
    return _result(
        name="Trendline Breakout v2",
        score=score,
        confidence=confidence,
        summary=summary,
        evidence=[f"نسبة حجم آخر شمعة: {volume_ratio:.2f}x", f"جودة ملاءمة خطوط الاتجاه: {fit_quality * 100:.1f}%"],
        signals=signals,
        features={"resistance": _sf(resistance, np.nan), "support": _sf(support, np.nan), "volume_ratio": volume_ratio, "atr": atr_last, "fit_quality": fit_quality, "trend_score": trend_score},
    )


def compute_advanced_technical_pack(df: pd.DataFrame, symbol: str = "", timeframe: str = "1d") -> Dict[str, Any]:
    data = _clean_ohlcv(df)
    items = {
        "rls_forecast": rls_forecast(data, timeframe=timeframe),
        "chaos_wrsi": chaos_weighted_rsi(data, timeframe=timeframe),
        "volume_profile_clusters": volume_profile_clusters(data, timeframe=timeframe),
        "trendline_breakout": trendline_breakout(data, timeframe=timeframe),
    }
    valid = [value for value in items.values() if not value.get("errors")]
    weights = np.array([max(1.0, _sf(x.get("confidence"))) for x in valid], dtype=float)
    scores = np.array([_sf(x.get("direction_score")) for x in valid], dtype=float)
    direction_score = float(np.average(scores, weights=weights)) if len(valid) else 0.0
    confidence = float(np.average(weights)) if len(valid) else 0.0
    agreement = 0.0
    if len(scores) >= 2:
        signs = np.sign(scores[np.abs(scores) >= 15])
        agreement = abs(float(np.mean(signs))) if len(signs) else 0.0
        confidence = min(100.0, confidence + agreement * 10.0)

    signals = [signal for value in items.values() for signal in value.get("signals", [])]
    evidence = [f"{value['name']}: {value['summary']}" for value in items.values()]
    features = {
        "direction_score": direction_score,
        "agreement": agreement,
        "rows": int(len(data)),
        "last_close": _sf(data["Close"].iloc[-1]) if not data.empty else None,
    }
    summary = "ميل فني إيجابي" if direction_score >= 15 else "ميل فني سلبي" if direction_score <= -15 else "ميل فني مختلط أو محايد"
    return {
        "meta": {"symbol": symbol, "timeframe": timeframe, "rows": int(len(data)), "schema_version": "2.0", "confirmation": "close"},
        "bias": _bias(direction_score),
        "direction_score": round(direction_score, 2),
        "confidence": round(confidence, 2),
        "summary": summary,
        "evidence": evidence,
        "signals": signals,
        "features": features,
        "errors": [error for value in items.values() for error in value.get("errors", [])],
        **items,
    }
