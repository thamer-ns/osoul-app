"""Deterministic SC-V90/SC-FXM feature pack for completed OHLCV candles.

The pack ports the indicator ideas that can be reproduced safely in Python:
confirmed pivots, BOS/CHoCH, direct breaks and role-reversal retests, bounded
range compression, validated channel geometry, fakeouts, Wyckoff-style sweeps,
compact supply/demand origins and guarded ATR/Fibonacci objectives.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

SC_FEATURE_VERSION = "8.0"
_FIB_TARGETS = (1.0, 1.236, 1.618)


@dataclass(frozen=True, slots=True)
class _Params:
    pivot: int
    structure_lookback: int
    range_lookback: int
    retest_window: int
    min_risk_atr: float
    max_risk_atr: float
    max_channel_slope_atr: float = 0.75
    minimum_width_consistency: float = 0.45


def _interval(value: Any) -> str:
    raw = str(value or "1d").strip().lower()
    return {
        "60m": "1h",
        "60min": "1h",
        "240m": "4h",
        "1w": "1wk",
        "week": "1wk",
        "weekly": "1wk",
        "month": "1mo",
        "monthly": "1mo",
    }.get(raw, raw)


def _params(interval: str) -> _Params:
    frame = _interval(interval)
    if frame in {"1m", "2m", "5m", "15m"}:
        return _Params(3, 120, 20, 10, 0.45, 2.8)
    if frame in {"30m", "1h", "4h"}:
        return _Params(4, 150, 24, 8, 0.50, 3.2)
    if frame == "1d":
        return _Params(5, 180, 30, 6, 0.55, 4.0)
    return _Params(4, 160, 26, 5, 0.60, 4.5)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    aliases = {str(column).strip().lower(): column for column in frame.columns}
    rename: dict[Any, str] = {}
    for wanted in ("open", "high", "low", "close", "volume"):
        source = aliases.get(wanted)
        if source is not None:
            rename[source] = wanted.title()
    output = frame.rename(columns=rename).copy(deep=True)
    required = ("Open", "High", "Low", "Close")
    if not all(column in output.columns for column in required):
        return pd.DataFrame()
    if "Volume" not in output.columns:
        output["Volume"] = 0.0
    for column in (*required, "Volume"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna(subset=list(required))
    valid = (
        (output["Open"] > 0)
        & (output["High"] > 0)
        & (output["Low"] > 0)
        & (output["Close"] > 0)
        & (output["High"] >= output[["Open", "Close"]].max(axis=1))
        & (output["Low"] <= output[["Open", "Close"]].min(axis=1))
    )
    output = output.loc[valid]
    return output[~output.index.duplicated(keep="last")].sort_index()


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["Close"].shift(1)
    true_range = pd.concat(
        (
            frame["High"] - frame["Low"],
            (frame["High"] - previous).abs(),
            (frame["Low"] - previous).abs(),
        ),
        axis=1,
    ).max(axis=1)
    return true_range.ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=min(period, 5),
    ).mean()


def _pivots(
    frame: pd.DataFrame,
    width: int,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    high_values = frame["High"].tolist()
    low_values = frame["Low"].tolist()
    for index in range(width, len(frame) - width):
        high_window = high_values[index - width : index + width + 1]
        low_window = low_values[index - width : index + width + 1]
        if high_values[index] >= max(high_window):
            highs.append((index, float(high_values[index])))
        if low_values[index] <= min(low_window):
            lows.append((index, float(low_values[index])))
    return highs, lows


def _project(
    first: tuple[int, float],
    second: tuple[int, float],
    target_index: int,
) -> float:
    first_index, first_price = first
    second_index, second_price = second
    if second_index == first_index:
        return second_price
    slope = (second_price - first_price) / float(second_index - first_index)
    return second_price + slope * float(target_index - second_index)


def _volume_context(frame: pd.DataFrame) -> dict[str, Any]:
    volumes = frame["Volume"].clip(lower=0)
    trusted = int((volumes > 0).sum()) >= min(20, max(10, len(frame) // 4))
    ratio: float | None = None
    if trusted and len(volumes) >= 11:
        baseline = float(volumes.iloc[-31:-1].median())
        current = float(volumes.iloc[-1])
        if baseline > 0:
            ratio = current / baseline
    return {
        "trusted": trusted,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "participation": bool(ratio is not None and ratio >= 1.10),
        "quiet": bool(ratio is not None and ratio <= 1.0),
    }


def _compact_zone(
    frame: pd.DataFrame,
    direction: int,
    atr_value: float,
) -> dict[str, Any] | None:
    sample = frame.iloc[-14:-1]
    if sample.empty:
        return None
    ranges = (sample["High"] - sample["Low"]).replace(0, pd.NA)
    bodies = (sample["Close"] - sample["Open"]).abs()
    compact = (bodies / ranges).fillna(1.0) <= 0.50
    opposite = (
        sample["Close"] < sample["Open"]
        if direction > 0
        else sample["Close"] > sample["Open"]
    )
    candidates = sample.loc[compact | opposite]
    if candidates.empty:
        return None
    anchor = candidates.iloc[-1]
    body_high = max(float(anchor["Open"]), float(anchor["Close"]))
    body_low = min(float(anchor["Open"]), float(anchor["Close"]))
    if direction > 0:
        proximal, distal, kind = body_high, float(anchor["Low"]), "demand"
    else:
        proximal, distal, kind = body_low, float(anchor["High"]), "supply"
    width = abs(proximal - distal)
    if width <= 0 or width > max(atr_value * 2.5, abs(proximal) * 0.08):
        return None
    return {
        "kind": kind,
        "proximal": proximal,
        "distal": distal,
        "width_atr": width / atr_value if atr_value > 0 else None,
    }


def _risk_plan(
    *,
    direction: int,
    price: float,
    atr_value: float,
    event_level: float | None,
    support: float,
    resistance: float,
    measured_target: float | None,
    zone: dict[str, Any] | None,
    params: _Params,
) -> dict[str, Any]:
    if direction not in {-1, 1} or event_level is None or atr_value <= 0:
        return {"valid": False, "reason": "no_confirmed_trigger"}
    entry = price
    stop_buffer = atr_value * 0.25
    if direction > 0:
        structural = support
        if zone and zone.get("kind") == "demand":
            structural = min(structural, float(zone["distal"]))
        stop = structural - stop_buffer
        risk = entry - stop
    else:
        structural = resistance
        if zone and zone.get("kind") == "supply":
            structural = max(structural, float(zone["distal"]))
        stop = structural + stop_buffer
        risk = stop - entry
    minimum = atr_value * params.min_risk_atr
    maximum = min(atr_value * params.max_risk_atr, price * 0.10)
    if not math.isfinite(risk) or risk <= 0:
        return {"valid": False, "reason": "invalid_stop_geometry"}
    if risk < minimum:
        risk = minimum
        stop = entry - risk if direction > 0 else entry + risk
    if risk > maximum:
        return {
            "valid": False,
            "reason": "stop_too_far",
            "risk_atr": risk / atr_value,
        }
    targets = [entry + direction * risk * multiple for multiple in _FIB_TARGETS]
    if measured_target is not None and direction * (measured_target - entry) > risk * 0.75:
        candidates = targets + [measured_target]
        candidates = sorted(candidates, reverse=direction < 0)
        unique: list[float] = []
        for value in candidates:
            if direction * (value - entry) <= 0:
                continue
            if not unique or abs(value - unique[-1]) > max(
                price * 0.0005,
                atr_value * 0.05,
            ):
                unique.append(value)
        if len(unique) >= 3:
            targets = unique[:3]
    return {
        "valid": True,
        "entry": entry,
        "stop": stop,
        "targets": targets[:3],
        "risk": risk,
        "risk_atr": risk / atr_value,
        "first_rr": abs(targets[0] - entry) / risk,
        "method": "structure_atr_fib_measured",
    }


def build_sc_feature_pack(
    frame: pd.DataFrame,
    interval: str = "1d",
) -> dict[str, Any]:
    data = _prepare(frame)
    canonical = _interval(interval)
    params = _params(canonical)
    minimum = max(60, params.structure_lookback // 2)
    if len(data) < minimum:
        return {
            "ok": False,
            "version": SC_FEATURE_VERSION,
            "interval": canonical,
            "reason": "insufficient_closed_candles",
            "have": int(len(data)),
            "need": minimum,
        }
    data = data.tail(max(params.structure_lookback + 40, 220))
    atr_value = _finite(_atr(data).iloc[-1]) or 0.0
    price = float(data["Close"].iloc[-1])
    if atr_value <= 0 or price <= 0:
        return {
            "ok": False,
            "version": SC_FEATURE_VERSION,
            "interval": canonical,
            "reason": "invalid_atr_or_price",
        }

    highs, lows = _pivots(data, params.pivot)
    if not highs or not lows:
        return {
            "ok": False,
            "version": SC_FEATURE_VERSION,
            "interval": canonical,
            "reason": "missing_confirmed_pivots",
        }
    recent_highs = [item for item in highs if item[0] >= len(data) - params.structure_lookback]
    recent_lows = [item for item in lows if item[0] >= len(data) - params.structure_lookback]
    recent_highs = recent_highs or highs
    recent_lows = recent_lows or lows
    last_high = recent_highs[-1][1]
    last_low = recent_lows[-1][1]
    previous_close = float(data["Close"].iloc[-2])
    current_high = float(data["High"].iloc[-1])
    current_low = float(data["Low"].iloc[-1])
    buffer = max(atr_value * 0.05, price * 0.0005)
    tolerance = max(atr_value * 0.15, price * 0.001)

    structure_bias = 0
    structure_label = "neutral_structure"
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        higher = (
            recent_highs[-1][1] > recent_highs[-2][1]
            and recent_lows[-1][1] > recent_lows[-2][1]
        )
        lower = (
            recent_highs[-1][1] < recent_highs[-2][1]
            and recent_lows[-1][1] < recent_lows[-2][1]
        )
        if higher:
            structure_bias, structure_label = 1, "confirmed_rising_structure"
        elif lower:
            structure_bias, structure_label = -1, "confirmed_falling_structure"

    event_direction = 0
    event_code = "NONE"
    event_label = "no_confirmed_trigger"
    event_level: float | None = None
    break_up = previous_close <= last_high + buffer and price > last_high + buffer
    break_down = previous_close >= last_low - buffer and price < last_low - buffer
    if break_up or break_down:
        event_direction = 1 if break_up else -1
        event_code = (
            "CHOCH_UP"
            if break_up and structure_bias < 0
            else "BOS_UP"
            if break_up
            else "CHOCH_DOWN"
            if structure_bias > 0
            else "BOS_DOWN"
        )
        event_label = "confirmed_structure_break"
        event_level = last_high if break_up else last_low

    range_sample = data.iloc[-params.range_lookback - 1 : -1]
    range_high = float(range_sample["High"].max())
    range_low = float(range_sample["Low"].min())
    range_width = range_high - range_low
    compressed = range_width <= atr_value * 2.5
    range_up = compressed and previous_close <= range_high + buffer and price > range_high + buffer
    range_down = compressed and previous_close >= range_low - buffer and price < range_low - buffer
    if event_direction == 0 and (range_up or range_down):
        event_direction = 1 if range_up else -1
        event_code = "RANGE_BREAK_UP" if range_up else "RANGE_BREAK_DOWN"
        event_label = "confirmed_compression_break"
        event_level = range_high if range_up else range_low

    prior_retest = data.iloc[-params.retest_window - 1 : -1]
    broke_up_recently = bool((prior_retest["Close"] > last_high + buffer).any())
    broke_down_recently = bool((prior_retest["Close"] < last_low - buffer).any())
    bullish_retest = (
        broke_up_recently
        and current_low <= last_high + tolerance
        and price > last_high
    )
    bearish_retest = (
        broke_down_recently
        and current_high >= last_low - tolerance
        and price < last_low
    )
    if bullish_retest or bearish_retest:
        event_direction = 1 if bullish_retest else -1
        event_code = "RETEST_UP" if bullish_retest else "RETEST_DOWN"
        event_label = "confirmed_role_reversal_retest"
        event_level = last_high if bullish_retest else last_low

    channel: dict[str, Any] = {
        "ready": False,
        "bias": 0,
        "quality": False,
        "width_consistency": None,
        "touches": 0,
    }
    measured_target: float | None = None
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        high_a, high_b = recent_highs[-2], recent_highs[-1]
        low_a, low_b = recent_lows[-2], recent_lows[-1]
        high_slope = (high_b[1] - high_a[1]) / max(1, high_b[0] - high_a[0])
        low_slope = (low_b[1] - low_a[1]) / max(1, low_b[0] - low_a[0])
        rising = high_b[1] > high_a[1] and low_b[1] > low_a[1]
        falling = high_b[1] < high_a[1] and low_b[1] < low_a[1]
        channel_bias = 1 if rising else -1 if falling else 0
        upper_now = _project(high_a, high_b, len(data) - 1)
        lower_now = _project(low_a, low_b, len(data) - 1)
        previous_upper = _project(high_a, high_b, len(data) - 2)
        previous_lower = _project(low_a, low_b, len(data) - 2)
        width_now = upper_now - lower_now
        anchor_index = min(high_a[0], low_a[0])
        width_before = (
            _project(high_a, high_b, anchor_index)
            - _project(low_a, low_b, anchor_index)
        )
        maximum_width = max(abs(width_now), abs(width_before))
        minimum_width = min(abs(width_now), abs(width_before))
        consistency = minimum_width / maximum_width if maximum_width > 0 else 0.0
        slope_atr = max(abs(high_slope), abs(low_slope)) / atr_value
        quality = bool(
            width_now > 0
            and slope_atr <= params.max_channel_slope_atr
            and consistency >= params.minimum_width_consistency
            and width_now <= atr_value * 10.0
        )
        channel.update(
            {
                "ready": quality,
                "bias": channel_bias,
                "converging": low_slope > 0 > high_slope,
                "quality": quality,
                "upper": upper_now,
                "lower": lower_now,
                "width": width_now if width_now > 0 else None,
                "width_atr": width_now / atr_value if width_now > 0 else None,
                "width_consistency": consistency,
                "slope_atr": slope_atr,
                "touches": 4,
            }
        )
        channel_up = quality and previous_close <= previous_upper + buffer and price > upper_now + buffer
        channel_down = quality and previous_close >= previous_lower - buffer and price < lower_now - buffer
        if event_direction == 0 and (channel_up or channel_down):
            event_direction = 1 if channel_up else -1
            event_code = "CHANNEL_BREAK_UP" if channel_up else "CHANNEL_BREAK_DOWN"
            event_label = "qualified_channel_break"
            event_level = upper_now if channel_up else lower_now
        if event_direction > 0 and quality:
            measured_target = upper_now + width_now
        elif event_direction < 0 and quality:
            measured_target = lower_now - width_now

    fakeout_up = bool(
        (prior_retest["Close"] > last_high + buffer).any()
        and price <= last_high
        and current_high > last_high
    )
    fakeout_down = bool(
        (prior_retest["Close"] < last_low - buffer).any()
        and price >= last_low
        and current_low < last_low
    )
    if fakeout_up or fakeout_down:
        event_direction = -1 if fakeout_up else 1
        event_code = "FAKEOUT_DOWN" if fakeout_up else "FAKEOUT_UP"
        event_label = "confirmed_fakeout_return"
        event_level = last_high if fakeout_up else last_low

    volume = _volume_context(data)
    current_range = max(current_high - current_low, 1e-12)
    body_ratio = abs(price - float(data["Open"].iloc[-1])) / current_range
    displacement = current_range / atr_value
    participation = bool(
        volume["participation"] or (body_ratio >= 0.60 and displacement >= 1.0)
    )

    sweep_support = float(range_sample["Low"].min())
    sweep_resistance = float(range_sample["High"].max())
    spring = (
        current_low < sweep_support - buffer
        and price > sweep_support
        and price > float(data["Open"].iloc[-1])
    )
    utad = (
        current_high > sweep_resistance + buffer
        and price < sweep_resistance
        and price < float(data["Open"].iloc[-1])
    )
    if event_direction == 0 and (spring or utad):
        event_direction = 1 if spring else -1
        event_code = "WYCKOFF_TEST_UP" if spring else "WYCKOFF_TEST_DOWN"
        event_label = "confirmed_spring_or_utad_test"
        event_level = sweep_support if spring else sweep_resistance

    direction = event_direction if event_direction else structure_bias
    zone = _compact_zone(data, direction, atr_value) if direction else None
    support = min(last_low, range_low)
    resistance = max(last_high, range_high)
    plan = _risk_plan(
        direction=direction,
        price=price,
        atr_value=atr_value,
        event_level=event_level,
        support=support,
        resistance=resistance,
        measured_target=measured_target,
        zone=zone,
        params=params,
    )

    structure_axis = 78 if direction and structure_bias == direction else 42 if direction else 30
    trigger_axis = (
        92
        if event_code.startswith(("RETEST", "CHOCH", "WYCKOFF"))
        else 84
        if event_direction
        else 25
    )
    participation_axis = 78 if participation else 48 if not volume["trusted"] else 30
    geometry_axis = 82 if plan.get("valid") else 45 if event_direction else 25
    channel_axis = 76 if channel.get("quality") else 40
    axes = {
        "structure": structure_axis,
        "trigger": trigger_axis,
        "participation": participation_axis,
        "risk_geometry": geometry_axis,
        "channel_range": channel_axis,
    }
    confidence = round(
        trigger_axis * 0.32
        + structure_axis * 0.24
        + geometry_axis * 0.22
        + participation_axis * 0.12
        + channel_axis * 0.10
    )
    qualified = bool(event_direction and confidence >= 62 and plan.get("valid"))

    reasons: list[str] = []
    warnings: list[str] = []
    if structure_bias:
        reasons.append(structure_label)
    if event_code != "NONE":
        reasons.append(event_label)
    if participation:
        reasons.append("qualified_participation")
    if channel.get("quality"):
        reasons.append("validated_channel_geometry")
    if compressed:
        reasons.append("bounded_range_compression")
    if not volume["trusted"]:
        warnings.append("volume_not_trusted_for_this_instrument")
    elif event_direction and not participation:
        warnings.append("trigger_without_strong_participation")
    if event_direction and not plan.get("valid"):
        warnings.append(str(plan.get("reason") or "invalid_risk_geometry"))

    def rounded(value: Any) -> Any:
        number = _finite(value)
        return round(number, 8) if number is not None else None

    if plan.get("valid"):
        plan = {
            **plan,
            "entry": rounded(plan.get("entry")),
            "stop": rounded(plan.get("stop")),
            "targets": [rounded(item) for item in plan.get("targets") or []],
            "risk": rounded(plan.get("risk")),
            "risk_atr": round(float(plan.get("risk_atr") or 0.0), 4),
            "first_rr": round(float(plan.get("first_rr") or 0.0), 4),
        }
    levels = {
        "support": rounded(support),
        "resistance": rounded(resistance),
        "event_level": rounded(event_level),
        "range_high": rounded(range_high),
        "range_low": rounded(range_low),
        "measured_target": rounded(measured_target),
    }
    if zone:
        zone = {
            key: rounded(value) if key != "kind" else value
            for key, value in zone.items()
        }
    channel = {
        key: rounded(value)
        if isinstance(value, (float, int)) and not isinstance(value, bool)
        else value
        for key, value in channel.items()
    }
    return {
        "ok": True,
        "version": SC_FEATURE_VERSION,
        "interval": canonical,
        "closed_candles_only": True,
        "rows": int(len(data)),
        "price": rounded(price),
        "atr": rounded(atr_value),
        "direction": direction,
        "structure_direction": structure_bias,
        "event_direction": event_direction,
        "event_code": event_code,
        "qualified": qualified,
        "confidence": max(0, min(100, confidence)),
        "evidence_axes": axes,
        "levels": levels,
        "range": {
            "compressed": compressed,
            "width": rounded(range_width),
            "width_atr": round(range_width / atr_value, 4),
        },
        "channel": channel,
        "volume": volume,
        "candle": {
            "body_ratio": round(body_ratio, 4),
            "displacement_atr": round(displacement, 4),
            "participation": participation,
        },
        "zone": zone,
        "risk_plan": plan,
        "reasons": list(dict.fromkeys(reasons)),
        "warnings": list(dict.fromkeys(warnings)),
    }


__all__ = ["SC_FEATURE_VERSION", "build_sc_feature_pack"]
