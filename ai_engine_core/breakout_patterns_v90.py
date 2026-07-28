"""SC-V90 compatible breakout-pattern engine for Osoli.

The Pine scripts remain the visual/alert implementation.  This module ports the
transport-independent model definitions into Python so the application can
calculate the same *classes* of setups from its own audited candles:
ascending/symmetrical triangles, rectangles, flags, pennants, wedges,
accumulation bases, previous-high breaks and break/role-reversal retests.

No live candle is used.  Pattern formation is informational; only a close beyond
the relevant boundary creates a confirmed signal.  Volume is required only when
it is meaningful for the asset/data source, matching the SC-FXM-V14 policy.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from candle_confirmation import completed_candles

ENGINE_VERSION = "SC-V90-PY-1.0"


@dataclass(frozen=True, slots=True)
class PatternResult:
    pattern_id: str
    name: str
    family: str
    direction: int
    status: str
    confidence: int
    boundary: float | None
    opposite_boundary: float | None
    height: float | None
    stop_reference: float | None
    measured_target: float | None
    reason: str
    volume_confirmed: bool | None
    detected_at: str


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    output = frame.copy()
    canonical = {str(column).strip().lower(): column for column in output.columns}
    rename = {}
    for name in ("open", "high", "low", "close", "volume"):
        if name in canonical:
            rename[canonical[name]] = name.title()
    output = output.rename(columns=rename)
    required = ["Open", "High", "Low", "Close"]
    if not all(column in output.columns for column in required):
        return pd.DataFrame()
    for column in required + (["Volume"] if "Volume" in output.columns else []):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    if "Volume" not in output.columns:
        output["Volume"] = 0.0
    output = output.dropna(subset=required)
    output = output[(output["High"] >= output[["Open", "Close"]].max(axis=1)) & (output["Low"] <= output[["Open", "Close"]].min(axis=1))]
    return output


def _atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    high = frame["High"]
    low = frame["Low"]
    close = frame["Close"]
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(length, min_periods=max(3, length // 2)).mean()


def _pivot_points(series: pd.Series, left: int, right: int, high: bool) -> list[tuple[int, float]]:
    values = pd.to_numeric(series, errors="coerce").to_numpy()
    points: list[tuple[int, float]] = []
    for index in range(left, len(values) - right):
        value = values[index]
        if not math.isfinite(float(value)):
            continue
        window = values[index - left : index + right + 1]
        valid = [float(item) for item in window if math.isfinite(float(item))]
        if not valid:
            continue
        extreme = max(valid) if high else min(valid)
        if math.isclose(float(value), extreme, rel_tol=1e-10, abs_tol=1e-12):
            points.append((index, float(value)))
    return points


def _line(points: list[tuple[int, float]]) -> tuple[float, float] | None:
    if len(points) < 2:
        return None
    x1, y1 = points[0]
    x2, y2 = points[-1]
    if x2 == x1:
        return None
    slope = (y2 - y1) / (x2 - x1)
    intercept = y2 - slope * x2
    return slope, intercept


def _at(line: tuple[float, float] | None, index: int) -> float | None:
    return line[0] * index + line[1] if line is not None else None


def _asset_volume_policy(symbol: str, frame: pd.DataFrame) -> dict[str, Any]:
    upper = str(symbol or "").upper()
    volume = pd.to_numeric(frame.get("Volume", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    has_volume = bool(len(volume) and (volume.tail(min(60, len(volume))) > 0).mean() >= 0.75)
    if "=X" in upper or upper.startswith("^"):
        mode = "optional"
        trusted = False
    elif "-USD" in upper or "USDT" in upper or "PERP" in upper:
        mode = "required"
        trusted = has_volume
    else:
        mode = "required" if has_volume else "optional"
        trusted = has_volume
    current = _finite(volume.iloc[-1]) if len(volume) else None
    average = _finite(volume.iloc[:-1].tail(20).mean()) if len(volume) > 1 else None
    ratio = current / average if current is not None and average and average > 0 else None
    confirmed = bool(ratio is not None and ratio >= 1.10) if trusted else None
    adverse = bool(ratio is not None and ratio >= 1.8) if trusted else False
    return {
        "mode": mode,
        "trusted": trusted,
        "has_volume": has_volume,
        "current": current,
        "average20": average,
        "relative_volume": ratio,
        "confirmed": confirmed,
        "adverse": adverse,
    }


def _close_break(
    previous_close: float,
    close: float,
    boundary: float,
    direction: int,
    buffer: float,
) -> bool:
    if direction > 0:
        return previous_close <= boundary + buffer and close > boundary + buffer
    return previous_close >= boundary - buffer and close < boundary - buffer


def _result(
    *,
    pattern_id: str,
    name: str,
    family: str,
    direction: int,
    confirmed: bool,
    confidence: int,
    boundary: float | None,
    opposite: float | None,
    height: float | None,
    close: float,
    volume_confirmed: bool | None,
    timestamp: str,
    reason: str,
) -> PatternResult:
    stop = opposite
    target = None
    if confirmed and height is not None and height > 0:
        target = close + direction * height
    return PatternResult(
        pattern_id=pattern_id,
        name=name,
        family=family,
        direction=direction,
        status="CONFIRMED" if confirmed else "FORMING",
        confidence=max(0, min(96, int(confidence))),
        boundary=round(boundary, 8) if boundary is not None else None,
        opposite_boundary=round(opposite, 8) if opposite is not None else None,
        height=round(height, 8) if height is not None else None,
        stop_reference=round(stop, 8) if stop is not None else None,
        measured_target=round(target, 8) if target is not None else None,
        reason=reason,
        volume_confirmed=volume_confirmed,
        detected_at=timestamp,
    )


def _rectangle(
    frame: pd.DataFrame,
    atr_value: float,
    volume: dict[str, Any],
    timestamp: str,
) -> list[PatternResult]:
    lookback = min(24, max(10, len(frame) // 5))
    base = frame.iloc[-(lookback + 1) : -1]
    if len(base) < 10:
        return []
    upper = float(base["High"].quantile(0.88))
    lower = float(base["Low"].quantile(0.12))
    height = upper - lower
    if height <= 0 or height > max(atr_value * 6.0, float(frame["Close"].iloc[-1]) * 0.12):
        return []
    touches_up = int((base["High"] >= upper - atr_value * 0.30).sum())
    touches_down = int((base["Low"] <= lower + atr_value * 0.30).sum())
    if touches_up < 2 or touches_down < 2:
        return []
    close = float(frame["Close"].iloc[-1])
    previous = float(frame["Close"].iloc[-2])
    buffer = atr_value * 0.05
    bullish = _close_break(previous, close, upper, 1, buffer)
    bearish = _close_break(previous, close, lower, -1, buffer)
    direction = 1 if bullish else -1 if bearish else 1 if close >= (upper + lower) / 2 else -1
    confirmed = bullish or bearish
    boundary = upper if direction > 0 else lower
    opposite = lower if direction > 0 else upper
    required_ok = volume["confirmed"] is not False if volume["mode"] == "required" else True
    confirmed = bool(confirmed and required_ok)
    confidence = 64 + min(12, (touches_up + touches_down) * 2) + (10 if confirmed else 0)
    if volume["confirmed"] is True:
        confidence += 6
    reason = f"نطاق أفقي بلمسات {touches_up}/{touches_down}; " + (
        "كسر مؤكد بالإغلاق" if confirmed else "الحد ما زال تحت المراقبة"
    )
    return [
        _result(
            pattern_id="rectangle",
            name="المستطيل / النطاق",
            family="range",
            direction=direction,
            confirmed=confirmed,
            confidence=confidence,
            boundary=boundary,
            opposite=opposite,
            height=height,
            close=close,
            volume_confirmed=volume["confirmed"],
            timestamp=timestamp,
            reason=reason,
        )
    ]


def _pivot_geometry_patterns(
    frame: pd.DataFrame,
    highs: list[tuple[int, float]],
    lows: list[tuple[int, float]],
    atr_value: float,
    volume: dict[str, Any],
    timestamp: str,
) -> list[PatternResult]:
    if len(highs) < 2 or len(lows) < 2:
        return []
    recent_highs = highs[-3:]
    recent_lows = lows[-3:]
    high_line = _line(recent_highs)
    low_line = _line(recent_lows)
    if high_line is None or low_line is None:
        return []
    index = len(frame) - 1
    upper = _at(high_line, index)
    lower = _at(low_line, index)
    if upper is None or lower is None or upper <= lower:
        return []
    previous_upper = _at(high_line, index - 1)
    previous_lower = _at(low_line, index - 1)
    close = float(frame["Close"].iloc[-1])
    previous_close = float(frame["Close"].iloc[-2])
    buffer = atr_value * 0.05
    upper_break = bool(previous_upper is not None and _close_break(previous_close, close, upper, 1, buffer))
    lower_break = bool(previous_lower is not None and _close_break(previous_close, close, lower, -1, buffer))
    high_slope, low_slope = high_line[0], low_line[0]
    width_now = upper - lower
    earliest_index = min(recent_highs[0][0], recent_lows[0][0])
    upper_then = _at(high_line, earliest_index)
    lower_then = _at(low_line, earliest_index)
    width_then = (upper_then - lower_then) if upper_then is not None and lower_then is not None else width_now
    converging = width_then > 0 and width_now < width_then * 0.82
    volume_ok = volume["confirmed"] is not False if volume["mode"] == "required" else True
    results: list[PatternResult] = []

    high_values = [value for _, value in recent_highs]
    low_values = [value for _, value in recent_lows]
    equal_highs = max(high_values) - min(high_values) <= atr_value * 0.45
    rising_lows = low_values[-1] > low_values[0] + atr_value * 0.15
    if equal_highs and rising_lows:
        resistance = sum(high_values) / len(high_values)
        confirmed = bool(_close_break(previous_close, close, resistance, 1, buffer) and volume_ok)
        height = resistance - min(low_values)
        results.append(
            _result(
                pattern_id="ascending_triangle",
                name="المثلث الصاعد",
                family="compression",
                direction=1,
                confirmed=confirmed,
                confidence=82 if confirmed else 68,
                boundary=resistance,
                opposite=lower,
                height=height,
                close=close,
                volume_confirmed=volume["confirmed"],
                timestamp=timestamp,
                reason="قمم شبه أفقية وقيعان صاعدة؛ " + ("اختراق مقاومة بإغلاق" if confirmed else "بانتظار إغلاق أعلى المقاومة"),
            )
        )

    if high_slope < 0 < low_slope and converging:
        direction = 1 if upper_break else -1 if lower_break else 1 if close >= (upper + lower) / 2 else -1
        confirmed = bool((upper_break or lower_break) and volume_ok)
        impulse_window = frame.iloc[max(0, earliest_index - 24) : earliest_index]
        impulse = (
            abs(float(impulse_window["Close"].iloc[-1] - impulse_window["Close"].iloc[0]))
            if len(impulse_window) >= 5
            else 0.0
        )
        pennant = impulse >= atr_value * 4.0
        results.append(
            _result(
                pattern_id="pennant" if pennant else "symmetrical_triangle",
                name="العلم المثلث" if pennant else "المثلث المتماثل",
                family="compression",
                direction=direction,
                confirmed=confirmed,
                confidence=(86 if pennant else 82) if confirmed else (70 if pennant else 67),
                boundary=upper if direction > 0 else lower,
                opposite=lower if direction > 0 else upper,
                height=max(width_then, width_now),
                close=close,
                volume_confirmed=volume["confirmed"],
                timestamp=timestamp,
                reason="ضغط بحدين مائلين متقاربين" + (" بعد اندفاع" if pennant else "") + (" وكسر بإغلاق" if confirmed else "؛ لم يحدث الكسر بعد"),
            )
        )

    if converging and high_slope > 0 and low_slope > 0 and lower_break:
        results.append(
            _result(
                pattern_id="rising_wedge",
                name="الوتد الصاعد",
                family="wedge",
                direction=-1,
                confirmed=volume_ok,
                confidence=84 if volume_ok else 70,
                boundary=lower,
                opposite=upper,
                height=max(width_then, width_now),
                close=close,
                volume_confirmed=volume["confirmed"],
                timestamp=timestamp,
                reason="خطان صاعدان متقاربان مع كسر الحد السفلي بإغلاق",
            )
        )
    if converging and high_slope < 0 and low_slope < 0 and upper_break:
        results.append(
            _result(
                pattern_id="falling_wedge",
                name="الوتد الهابط",
                family="wedge",
                direction=1,
                confirmed=volume_ok,
                confidence=84 if volume_ok else 70,
                boundary=upper,
                opposite=lower,
                height=max(width_then, width_now),
                close=close,
                volume_confirmed=volume["confirmed"],
                timestamp=timestamp,
                reason="خطان هابطان متقاربان مع اختراق الحد العلوي بإغلاق",
            )
        )
    return results


def _flag(
    frame: pd.DataFrame,
    atr_value: float,
    volume: dict[str, Any],
    timestamp: str,
) -> list[PatternResult]:
    if len(frame) < 45:
        return []
    impulse = frame.iloc[-45:-20]
    channel = frame.iloc[-20:-1]
    impulse_move = float(impulse["Close"].iloc[-1] - impulse["Close"].iloc[0])
    if abs(impulse_move) < atr_value * 4.0:
        return []
    direction = 1 if impulse_move > 0 else -1
    x = list(range(len(channel)))
    high_line = _line([(i, float(value)) for i, value in zip(x, channel["High"], strict=True)])
    low_line = _line([(i, float(value)) for i, value in zip(x, channel["Low"], strict=True)])
    if high_line is None or low_line is None:
        return []
    counter_trend = high_line[0] < 0 and low_line[0] < 0 if direction > 0 else high_line[0] > 0 and low_line[0] > 0
    roughly_parallel = abs(high_line[0] - low_line[0]) <= max(atr_value * 0.03, abs(high_line[0]) * 0.55)
    if not counter_trend or not roughly_parallel:
        return []
    upper = _at(high_line, len(channel))
    lower = _at(low_line, len(channel))
    if upper is None or lower is None:
        return []
    close = float(frame["Close"].iloc[-1])
    previous = float(frame["Close"].iloc[-2])
    boundary = upper if direction > 0 else lower
    opposite = lower if direction > 0 else upper
    confirmed = _close_break(previous, close, boundary, direction, atr_value * 0.05)
    volume_ok = volume["confirmed"] is not False if volume["mode"] == "required" else True
    confirmed = bool(confirmed and volume_ok)
    height = float(channel["High"].max() - channel["Low"].min())
    return [
        _result(
            pattern_id="flag",
            name="الراية",
            family="channel",
            direction=direction,
            confirmed=confirmed,
            confidence=86 if confirmed else 69,
            boundary=boundary,
            opposite=opposite,
            height=height,
            close=close,
            volume_confirmed=volume["confirmed"],
            timestamp=timestamp,
            reason="قناة تصحيحية عكس اندفاع سابق؛ " + ("كسر حد القناة بإغلاق" if confirmed else "بانتظار كسر القناة"),
        )
    ]


def _accumulation_and_structural(
    frame: pd.DataFrame,
    highs: list[tuple[int, float]],
    lows: list[tuple[int, float]],
    atr_value: float,
    volume: dict[str, Any],
    timestamp: str,
) -> list[PatternResult]:
    results: list[PatternResult] = []
    close = float(frame["Close"].iloc[-1])
    previous = float(frame["Close"].iloc[-2])
    buffer = atr_value * 0.05
    volume_ok = volume["confirmed"] is not False if volume["mode"] == "required" else True

    if len(frame) >= 55:
        preceding = frame.iloc[-55:-25]
        base = frame.iloc[-25:-1]
        decline = float(preceding["Close"].iloc[-1] - preceding["Close"].iloc[0])
        upper = float(base["High"].quantile(0.90))
        lower = float(base["Low"].quantile(0.10))
        height = upper - lower
        narrow = height <= atr_value * 5.0
        confirmed = bool(decline <= -atr_value * 3.0 and narrow and _close_break(previous, close, upper, 1, buffer) and volume_ok)
        if decline <= -atr_value * 3.0 and narrow:
            results.append(
                _result(
                    pattern_id="accumulation_base",
                    name="قاعدة التجميع",
                    family="base",
                    direction=1,
                    confirmed=confirmed,
                    confidence=88 if confirmed else 66,
                    boundary=upper,
                    opposite=lower,
                    height=height,
                    close=close,
                    volume_confirmed=volume["confirmed"],
                    timestamp=timestamp,
                    reason="نطاق بعد هبوط ممتد؛ " + ("اختراق أعلى القاعدة بجودة وحجم" if confirmed else "القاعدة تحت المراقبة"),
                )
            )

    previous_highs = [item for item in highs if item[0] < len(frame) - 2]
    if previous_highs:
        pivot_index, pivot = previous_highs[-1]
        recent_enough = len(frame) - 1 - pivot_index <= 120
        if recent_enough and _close_break(previous, close, pivot, 1, buffer):
            stop = float(frame["Low"].iloc[max(0, pivot_index):].min())
            results.append(
                _result(
                    pattern_id="previous_high_break",
                    name="اختراق قمة سابقة",
                    family="structure",
                    direction=1,
                    confirmed=volume_ok,
                    confidence=84 if volume_ok else 72,
                    boundary=pivot,
                    opposite=stop,
                    height=max(pivot - stop, atr_value),
                    close=close,
                    volume_confirmed=volume["confirmed"],
                    timestamp=timestamp,
                    reason="إغلاق فوق Swing High أو مقاومة سابقة",
                )
            )

    previous_lows = [item for item in lows if item[0] < len(frame) - 5]
    if previous_lows:
        _pivot_index, support = previous_lows[-1]
        last_eight = frame.iloc[-9:-1]
        broke = bool((last_eight["Close"] < support - buffer).any())
        retest = float(frame["High"].iloc[-1]) >= support - atr_value * 0.15
        rejected = close < support - buffer and close < float(frame["Open"].iloc[-1])
        if broke and retest and rejected:
            results.append(
                _result(
                    pattern_id="role_reversal",
                    name="كسر وتحول / إعادة اختبار",
                    family="structure",
                    direction=-1,
                    confirmed=True,
                    confidence=89,
                    boundary=support,
                    opposite=float(frame["High"].iloc[-1]),
                    height=max(support - float(frame["Low"].iloc[-1]), atr_value),
                    close=close,
                    volume_confirmed=volume["confirmed"],
                    timestamp=timestamp,
                    reason="دعم مكسور أعيد اختباره ثم رُفض بإغلاق تحته",
                )
            )
    return results


def _deduplicate(results: list[PatternResult]) -> list[PatternResult]:
    strongest: dict[tuple[str, int, str], PatternResult] = {}
    for item in results:
        key = (item.family, item.direction, item.status)
        previous = strongest.get(key)
        if previous is None or item.confidence > previous.confidence:
            strongest[key] = item
    return sorted(
        strongest.values(),
        key=lambda item: (item.status == "CONFIRMED", item.confidence),
        reverse=True,
    )


def analyze_breakout_patterns(
    frame: pd.DataFrame,
    *,
    symbol: str = "",
    timeframe: str = "1d",
) -> dict[str, Any]:
    normalized = _normalise_frame(frame)
    closed = completed_candles(normalized, interval=timeframe)
    if closed.empty or len(closed) < 60:
        return {
            "name": "SC-V90 breakout patterns",
            "version": ENGINE_VERSION,
            "ok": False,
            "errors": ["بيانات الشموع المكتملة غير كافية"],
            "patterns": [],
            "signals": [],
            "features": {},
            "evidence": [],
        }
    closed = closed.tail(320).copy()
    atr_series = _atr(closed)
    atr_value = _finite(atr_series.iloc[-1])
    if atr_value is None or atr_value <= 0:
        return {
            "name": "SC-V90 breakout patterns",
            "version": ENGINE_VERSION,
            "ok": False,
            "errors": ["تعذر حساب ATR صالح"],
            "patterns": [],
            "signals": [],
            "features": {},
            "evidence": [],
        }
    frame_key = str(timeframe or "1d").lower()
    pivot_bars = 2 if frame_key in {"1m", "5m", "15m", "30m", "1h", "60m"} else 3 if frame_key in {"1d", "4h"} else 4
    highs = _pivot_points(closed["High"], pivot_bars, pivot_bars, high=True)
    lows = _pivot_points(closed["Low"], pivot_bars, pivot_bars, high=False)
    volume = _asset_volume_policy(symbol, closed)
    timestamp = str(closed.index[-1])

    raw: list[PatternResult] = []
    raw.extend(_rectangle(closed, atr_value, volume, timestamp))
    raw.extend(_pivot_geometry_patterns(closed, highs, lows, atr_value, volume, timestamp))
    raw.extend(_flag(closed, atr_value, volume, timestamp))
    raw.extend(_accumulation_and_structural(closed, highs, lows, atr_value, volume, timestamp))
    patterns = _deduplicate(raw)
    confirmed = [item for item in patterns if item.status == "CONFIRMED"]
    forming = [item for item in patterns if item.status == "FORMING"]
    signed = sum(item.direction * item.confidence for item in confirmed)
    if not confirmed:
        signed = sum(item.direction * item.confidence * 0.25 for item in forming[:2])
    denominator = sum(item.confidence for item in confirmed) or sum(item.confidence * 0.25 for item in forming[:2]) or 1.0
    direction_score = max(-100.0, min(100.0, signed / denominator * 100.0))
    confidence = max((item.confidence for item in confirmed), default=max((item.confidence for item in forming), default=0))
    bias = "bullish" if direction_score >= 20 else "bearish" if direction_score <= -20 else "neutral"

    signals = [
        {
            "type": "SC-V90",
            "kind": item.name,
            "direction": "buy" if item.direction > 0 else "sell",
            "price": float(closed["Close"].iloc[-1]),
            "level": item.boundary,
            "stop_reference": item.stop_reference,
            "measured_target": item.measured_target,
            "reason": item.reason,
            "volume_confirmed": item.volume_confirmed,
            "confirmed_on_close": True,
        }
        for item in confirmed
    ]
    evidence = [
        f"{item.name}: {item.reason} ({item.confidence}/100)"
        for item in patterns[:8]
    ]
    features: dict[str, Any] = {
        "breakout_pattern_count": len(patterns),
        "breakout_confirmed_count": len(confirmed),
        "breakout_forming_count": len(forming),
        "breakout_direction_score": round(direction_score, 3),
        "breakout_bullish": int(any(item.direction > 0 for item in confirmed)),
        "breakout_bearish": int(any(item.direction < 0 for item in confirmed)),
        "volume_trusted": int(bool(volume["trusted"])),
        "relative_volume": volume["relative_volume"],
    }
    for item in patterns:
        features[f"pattern_{item.pattern_id}_{item.status.lower()}"] = 1
    primary = confirmed[0] if confirmed else forming[0] if forming else None
    return {
        "name": "SC-V90 breakout patterns",
        "version": ENGINE_VERSION,
        "ok": True,
        "bias": bias,
        "direction_score": round(direction_score, 2),
        "confidence": confidence,
        "summary": (
            f"{len(confirmed)} نموذج اختراق مؤكد و{len(forming)} نموذج تحت التكوين"
            if patterns
            else "لا يوجد نموذج اختراق واضح على آخر إغلاق"
        ),
        "patterns": [asdict(item) for item in patterns],
        "signals": signals,
        "features": features,
        "evidence": evidence,
        "volume_policy": volume,
        "risk_reference": (
            {
                "pattern": primary.name,
                "direction": "buy" if primary.direction > 0 else "sell",
                "boundary": primary.boundary,
                "stop_reference": primary.stop_reference,
                "measured_target": primary.measured_target,
                "height": primary.height,
            }
            if primary is not None
            else {}
        ),
        "closed_candles_only": True,
        "last_closed_bar": timestamp,
        "errors": [],
    }


__all__ = ["ENGINE_VERSION", "analyze_breakout_patterns"]
