"""SC-V92.5 / SC-FXM-V16 decision and risk contract for closed candles.

This module ports the server-side parts of the Pine indicators that must agree
between Osoli and the Telegram bot. Chart drawings remain a TradingView concern;
the Python contract focuses on deterministic decision priority, lifecycle events,
plan geometry and explainability.

Priority contract:
1. confirmed horizontal multi-touch support/resistance clusters;
2. confirmed swing pivots (the HH/HL/LH/LL structure source);
3. supply/demand, range/Wyckoff, channels, Fibonacci and key-candle references.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

SC_FEATURE_VERSION = "92.5-PY"
SC_INDICATOR_SOURCES = ("SC-V92-I", "SC-V92-D", "SC-FXM-V16")


@dataclass(frozen=True, slots=True)
class _Params:
    pivot: int
    structure_lookback: int
    range_lookback: int
    retest_window: int
    min_risk_atr: float
    max_risk_atr: float
    minimum_t1_r: float = 1.0
    short_plan_min_r: float = 0.75
    sr_stored_pivots: int = 40
    sr_minimum_touches: int = 2
    sr_tolerance_atr: float = 0.35
    sr_maximum_age_bars: int = 300
    break_buffer_atr: float = 0.05
    retest_tolerance_atr: float = 0.15
    stop_buffer_atr: float = 0.25
    evidence_minimum_percent: float = 55.0
    early_evidence_discount: float = 7.5


def _interval(value: Any) -> str:
    raw = str(value or "1d").strip().lower()
    return {
        "1min": "1m",
        "60m": "1h",
        "60min": "1h",
        "240m": "4h",
        "1wk": "1w",
        "week": "1w",
        "weekly": "1w",
        "month": "1mo",
        "monthly": "1mo",
    }.get(raw, raw)


def _params(interval: str) -> _Params:
    frame = _interval(interval)
    if frame in {"1m", "2m", "5m", "15m"}:
        return _Params(2, 120, 20, 10, 0.45, 1.80 if frame == "1m" else 2.20)
    if frame == "30m":
        return _Params(2, 150, 24, 8, 0.60, 2.40)
    if frame == "1h":
        return _Params(3, 150, 24, 8, 0.65, 2.70)
    if frame == "4h":
        return _Params(3, 180, 30, 8, 0.75, 3.10)
    if frame == "1d":
        return _Params(3, 200, 30, 8, 0.85, 3.50)
    if frame == "1w":
        return _Params(2, 220, 26, 6, 1.00, 4.00)
    if frame == "1mo":
        return _Params(2, 240, 24, 5, 1.10, 4.50)
    return _Params(3, 180, 26, 6, 0.85, 3.50)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _rounded(value: Any) -> Any:
    number = _finite(value)
    return round(number, 8) if number is not None else None


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
        & (output["High"] >= output["Low"])
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


def _strong_cluster(
    pivots: list[tuple[int, float]],
    *,
    current_index: int,
    tolerance: float,
    minimum_touches: int,
    maximum_age_bars: int,
    stored: int,
    kind: str,
) -> dict[str, Any] | None:
    eligible = [
        item
        for item in pivots[-stored:]
        if current_index - item[0] <= maximum_age_bars
    ]
    selected: dict[str, Any] | None = None
    for _candidate_index, candidate_price in eligible:
        members = [
            item
            for item in eligible
            if abs(item[1] - candidate_price) <= tolerance
        ]
        if len(members) < minimum_touches:
            continue
        prices = [item[1] for item in members]
        recent = max(item[0] for item in members)
        candidate = {
            "kind": kind,
            "level": sum(prices) / len(prices),
            "low": min(prices),
            "high": max(prices),
            "touches": len(members),
            "recent_bar": recent,
            "age_bars": current_index - recent,
            "member_bars": tuple(sorted(item[0] for item in members)),
        }
        if selected is None:
            selected = candidate
            continue
        if (candidate["touches"], candidate["recent_bar"]) > (
            selected["touches"], selected["recent_bar"]
        ):
            selected = candidate
    return selected


def _nearest_pivot(
    pivots: Iterable[tuple[int, float]],
    *,
    price: float,
    direction: int,
    minimum_distance: float,
    maximum_age_bars: int,
    current_index: int,
    exclude_prices: Iterable[float] = (),
    tolerance: float = 0.0,
) -> tuple[int, float] | None:
    excluded = tuple(float(value) for value in exclude_prices)
    candidates: list[tuple[float, int, float]] = []
    for index, level in pivots:
        if current_index - index > maximum_age_bars:
            continue
        if direction > 0 and level < price + minimum_distance:
            continue
        if direction < 0 and level > price - minimum_distance:
            continue
        if any(abs(level - used) <= tolerance for used in excluded):
            continue
        candidates.append((abs(level - price), index, level))
    if not candidates:
        return None
    _, index, level = min(candidates, key=lambda item: (item[0], -item[1]))
    return index, level


def _compact_zone(
    frame: pd.DataFrame,
    direction: int,
    atr_value: float,
) -> dict[str, Any] | None:
    sample = frame.iloc[-14:-1]
    if sample.empty:
        return None
    spreads = (sample["High"] - sample["Low"]).replace(0.0, pd.NA)
    bodies = (sample["Close"] - sample["Open"]).abs()
    compact = (bodies / spreads).fillna(1.0) <= 0.50
    opposite = sample["Close"] < sample["Open"] if direction > 0 else sample["Close"] > sample["Open"]
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
        "width_atr": width / atr_value,
    }


def _volume_policy(asset_class: str, market: str) -> str:
    asset = str(asset_class or "").strip().lower()
    market_text = str(market or "").strip().upper()
    if asset in {"stock", "fund", "dr", "crypto", "future", "futures"}:
        return "required"
    if asset in {"forex", "index", "cfd", "bond", "commodity", "spot"}:
        return "price_first"
    if market_text in {"SAUDI", "US", "US_OPTIONS", "CRYPTO"}:
        return "required"
    return "price_first"


def _volume_context(
    frame: pd.DataFrame,
    *,
    asset_class: str,
    market: str,
) -> dict[str, Any]:
    policy = _volume_policy(asset_class, market)
    volumes = frame["Volume"].clip(lower=0.0)
    positive = volumes.iloc[-31:-1]
    positive = positive[positive > 0]
    baseline = float(positive.median()) if len(positive) >= 10 else 0.0
    current = float(volumes.iloc[-1])
    ratio = current / baseline if baseline > 0 else None
    trusted = policy == "required" and ratio is not None
    return {
        "policy": policy,
        "trusted": trusted,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "participation": bool(ratio is not None and ratio >= 1.10),
        "quiet": bool(ratio is not None and ratio <= 1.0),
        "method": "closed_bar_median_30",
    }


def _role_state(
    frame: pd.DataFrame,
    cluster: dict[str, Any] | None,
    *,
    direction: int,
    buffer: float,
    retest_window: int,
    tolerance: float,
) -> dict[str, Any]:
    if cluster is None or len(frame) < retest_window + 2:
        return {"broken_recently": False, "retest": False, "failed": False, "break_bar": None}
    closes = frame["Close"].tolist()
    highs = frame["High"].tolist()
    lows = frame["Low"].tolist()
    start = max(1, len(frame) - retest_window - 1)
    break_bar: int | None = None
    for index in range(start, len(frame) - 1):
        if direction > 0:
            crossed = closes[index - 1] <= cluster["high"] + buffer and closes[index] > cluster["high"] + buffer
        else:
            crossed = closes[index - 1] >= cluster["low"] - buffer and closes[index] < cluster["low"] - buffer
        if crossed:
            break_bar = index
    current_close = closes[-1]
    if direction > 0:
        retest = bool(break_bar is not None and lows[-1] <= cluster["high"] + tolerance and current_close > cluster["high"])
        failed = bool(break_bar is not None and current_close < cluster["low"] - buffer)
    else:
        retest = bool(break_bar is not None and highs[-1] >= cluster["low"] - tolerance and current_close < cluster["low"])
        failed = bool(break_bar is not None and current_close > cluster["high"] + buffer)
    return {
        "broken_recently": break_bar is not None,
        "retest": retest and not failed,
        "failed": failed,
        "break_bar": break_bar,
    }


def _event_contract(
    frame: pd.DataFrame,
    *,
    support_cluster: dict[str, Any] | None,
    resistance_cluster: dict[str, Any] | None,
    last_low: float,
    last_high: float,
    structure_direction: int,
    atr_value: float,
    params: _Params,
) -> dict[str, Any]:
    previous_close = float(frame["Close"].iloc[-2])
    close = float(frame["Close"].iloc[-1])
    high = float(frame["High"].iloc[-1])
    low = float(frame["Low"].iloc[-1])
    open_value = float(frame["Open"].iloc[-1])
    buffer = max(params.break_buffer_atr * atr_value, close * 0.0005)
    tolerance = max(params.retest_tolerance_atr * atr_value, close * 0.001)
    bull_role = _role_state(frame, resistance_cluster, direction=1, buffer=buffer, retest_window=params.retest_window, tolerance=tolerance)
    bear_role = _role_state(frame, support_cluster, direction=-1, buffer=buffer, retest_window=params.retest_window, tolerance=tolerance)
    events: list[dict[str, Any]] = []

    def add(code: str, direction: int, priority: int, level: float, source: str, trigger: str) -> None:
        events.append({"code": code, "direction": direction, "priority": priority, "level": level, "source": source, "trigger": trigger})

    if resistance_cluster:
        break_up = previous_close <= resistance_cluster["high"] + buffer and close > resistance_cluster["high"] + buffer
        fakeout_down = high > resistance_cluster["high"] + buffer and close <= resistance_cluster["high"]
        if bull_role["retest"]:
            add("CLUSTER_RETEST_UP", 1, 340, resistance_cluster["level"], "sr_cluster", "confirmed_role_reversal")
        elif fakeout_down:
            add("CLUSTER_FAKEOUT_DOWN", -1, 330, resistance_cluster["level"], "sr_cluster", "confirmed_close_return")
        elif break_up:
            add("CLUSTER_CHOCH_UP" if structure_direction < 0 else "CLUSTER_BOS_UP", 1, 240, resistance_cluster["high"], "sr_cluster", "confirmed_close_break")
    if support_cluster:
        break_down = previous_close >= support_cluster["low"] - buffer and close < support_cluster["low"] - buffer
        fakeout_up = low < support_cluster["low"] - buffer and close >= support_cluster["low"]
        if bear_role["retest"]:
            add("CLUSTER_RETEST_DOWN", -1, 340, support_cluster["level"], "sr_cluster", "confirmed_role_reversal")
        elif fakeout_up:
            add("CLUSTER_FAKEOUT_UP", 1, 330, support_cluster["level"], "sr_cluster", "confirmed_close_return")
        elif break_down:
            add("CLUSTER_CHOCH_DOWN" if structure_direction > 0 else "CLUSTER_BOS_DOWN", -1, 240, support_cluster["low"], "sr_cluster", "confirmed_close_break")

    prior = frame.iloc[-params.retest_window - 1 : -1]
    pivot_broke_up = bool((prior["Close"] > last_high + buffer).any())
    pivot_broke_down = bool((prior["Close"] < last_low - buffer).any())
    if pivot_broke_up and low <= last_high + tolerance and close > last_high:
        add("PIVOT_RETEST_UP", 1, 300, last_high, "pivot", "confirmed_role_reversal")
    if pivot_broke_down and high >= last_low - tolerance and close < last_low:
        add("PIVOT_RETEST_DOWN", -1, 300, last_low, "pivot", "confirmed_role_reversal")
    if previous_close <= last_high + buffer and close > last_high + buffer:
        add("PIVOT_CHOCH_UP" if structure_direction < 0 else "PIVOT_BOS_UP", 1, 200, last_high, "pivot", "confirmed_close_break")
    if previous_close >= last_low - buffer and close < last_low - buffer:
        add("PIVOT_CHOCH_DOWN" if structure_direction > 0 else "PIVOT_BOS_DOWN", -1, 200, last_low, "pivot", "confirmed_close_break")

    location_low = support_cluster["low"] if support_cluster else last_low
    location_high = resistance_cluster["high"] if resistance_cluster else last_high
    if low < location_low - buffer and close > location_low and close > open_value:
        add("EARLY_SWEEP_UP", 1, 100, location_low, "sr_cluster" if support_cluster else "pivot", "confirmed_recovery_close")
    if high > location_high + buffer and close < location_high and close < open_value:
        add("EARLY_SWEEP_DOWN", -1, 100, location_high, "sr_cluster" if resistance_cluster else "pivot", "confirmed_recovery_close")
    return {
        "selected": max(events, key=lambda item: item["priority"], default=None),
        "candidates": sorted(events, key=lambda item: item["priority"], reverse=True),
        "buffer": buffer,
        "tolerance": tolerance,
        "role_reversal": {"bullish": bull_role, "bearish": bear_role},
    }


def _opposition_veto(
    *,
    direction: int,
    price: float,
    atr_value: float,
    event: dict[str, Any] | None,
    support_cluster: dict[str, Any] | None,
    resistance_cluster: dict[str, Any] | None,
) -> dict[str, Any]:
    if direction > 0 and resistance_cluster:
        distance = resistance_cluster["low"] - price
        broken = bool(event and event["direction"] > 0 and event["source"] == "sr_cluster" and event["trigger"] == "confirmed_close_break")
        near = -0.15 * atr_value <= distance <= 1.0 * atr_value
        blocked = near and not broken and not (event and event["code"] == "CLUSTER_RETEST_UP")
        return {"blocked": blocked, "side": "resistance", "distance_atr": distance / atr_value, "reason": "active_resistance_cluster_opposes_long" if blocked else ""}
    if direction < 0 and support_cluster:
        distance = price - support_cluster["high"]
        broken = bool(event and event["direction"] < 0 and event["source"] == "sr_cluster" and event["trigger"] == "confirmed_close_break")
        near = -0.15 * atr_value <= distance <= 1.0 * atr_value
        blocked = near and not broken and not (event and event["code"] == "CLUSTER_RETEST_DOWN")
        return {"blocked": blocked, "side": "support", "distance_atr": distance / atr_value, "reason": "active_support_cluster_opposes_short" if blocked else ""}
    return {"blocked": False, "side": "", "distance_atr": None, "reason": ""}


def _evidence(
    frame: pd.DataFrame,
    *,
    event: dict[str, Any] | None,
    structure_direction: int,
    direction: int,
    volume: dict[str, Any],
    atr_value: float,
    veto: dict[str, Any],
    params: _Params,
) -> dict[str, Any]:
    current = frame.iloc[-1]
    spread = max(float(current["High"] - current["Low"]), 1e-12)
    body_ratio = abs(float(current["Close"] - current["Open"])) / spread
    close_location = (float(current["Close"]) - float(current["Low"])) / spread
    displacement = spread / atr_value
    price_participation = body_ratio >= 0.60 and displacement >= 1.0
    participation = bool(volume["participation"] or price_participation)
    volume_pass = volume["policy"] != "required" or participation
    structure_support = bool(direction and (structure_direction == direction or (event and "CHOCH" in event["code"])))
    location_support = bool(event and event["source"] in {"sr_cluster", "pivot"})
    axes = {
        "structure": 78 if structure_support else 36 if direction else 20,
        "participation": 76 if volume_pass else 28,
        "location": 90 if event and event["source"] == "sr_cluster" else 76 if location_support else 35,
        "trigger": 94 if event and event["priority"] >= 300 else 86 if event and event["priority"] >= 200 else 72 if event else 20,
    }
    own_count = sum(value >= 60 for value in axes.values())
    opposition_count = int(bool(veto.get("blocked"))) + int(structure_direction == -direction and not (event and "CHOCH" in event["code"]))
    score = round(sum(axes.values()) / len(axes))
    direct_break = bool(event and event["priority"] in {200, 240})
    close_quality = close_location >= 0.72 if direction > 0 else close_location <= 0.28
    direct_quality = bool(not direct_break or (body_ratio >= 0.55 and close_quality and volume_pass and own_count >= 2 and own_count >= opposition_count + 2))
    threshold = params.evidence_minimum_percent - (params.early_evidence_discount if event and event["priority"] == 100 else 0.0)
    exceptional = bool(event and event["priority"] >= 300 and axes["trigger"] >= 90 and axes["location"] >= 76)
    qualified = bool(event and not veto.get("blocked") and direct_quality and score >= threshold and (own_count >= 2 or exceptional) and own_count > opposition_count)
    return {
        "axes": axes,
        "own_count": own_count,
        "opposition_count": opposition_count,
        "score_percent": score,
        "minimum_percent": threshold,
        "qualified": qualified,
        "exceptional_single_trigger": exceptional,
        "direct_break_quality": direct_quality,
        "body_ratio": round(body_ratio, 4),
        "close_location": round(close_location, 4),
        "displacement_atr": round(displacement, 4),
        "participation": participation,
    }


def _candidate(price: float | None, source: str, priority: int) -> dict[str, Any] | None:
    value = _finite(price)
    if value is None or value <= 0:
        return None
    return {"price": value, "source": source, "priority": priority}


def _risk_plan(
    frame: pd.DataFrame,
    *,
    direction: int,
    atr_value: float,
    event: dict[str, Any] | None,
    support_cluster: dict[str, Any] | None,
    resistance_cluster: dict[str, Any] | None,
    highs: list[tuple[int, float]],
    lows: list[tuple[int, float]],
    last_high: float,
    last_low: float,
    zone: dict[str, Any] | None,
    range_high: float,
    range_low: float,
    params: _Params,
    qualified: bool,
) -> dict[str, Any]:
    if direction not in {-1, 1} or event is None or not qualified:
        return {"valid": False, "reason": "no_qualified_confirmed_trigger", "target_count": 0}
    entry = float(frame["Close"].iloc[-1])
    current_index = len(frame) - 1
    stop_buffer = atr_value * params.stop_buffer_atr
    stop_source = ""
    protective_level: float | None = None
    if direction > 0:
        if support_cluster and support_cluster["high"] < entry:
            protective_level = support_cluster["low"]
            stop_source = "protective_support_cluster"
        elif last_low < entry:
            protective_level = last_low
            stop_source = "confirmed_pivot_low"
        elif zone and zone.get("kind") == "demand":
            protective_level = float(zone["distal"])
            stop_source = "demand_zone"
        stop = protective_level - stop_buffer if protective_level is not None else None
    else:
        if resistance_cluster and resistance_cluster["low"] > entry:
            protective_level = resistance_cluster["high"]
            stop_source = "protective_resistance_cluster"
        elif last_high > entry:
            protective_level = last_high
            stop_source = "confirmed_pivot_high"
        elif zone and zone.get("kind") == "supply":
            protective_level = float(zone["distal"])
            stop_source = "supply_zone"
        stop = protective_level + stop_buffer if protective_level is not None else None
    if stop is None:
        return {"valid": False, "reason": "missing_structural_invalidation", "target_count": 0}
    risk = entry - stop if direction > 0 else stop - entry
    if not math.isfinite(risk) or risk <= 0:
        return {"valid": False, "reason": "invalid_stop_geometry", "target_count": 0}
    risk_atr = risk / atr_value
    if risk_atr > params.max_risk_atr:
        return {"valid": False, "reason": "stop_too_far", "risk_atr": risk_atr, "stop_source": stop_source, "target_count": 0}
    target_basis = max(risk, atr_value * params.min_risk_atr)
    min_distance = max(atr_value * 0.05, entry * 0.0005)
    pivot_pool = highs if direction > 0 else lows
    used: list[float] = []
    first_pivot = _nearest_pivot(pivot_pool, price=entry, direction=direction, minimum_distance=min_distance, maximum_age_bars=params.sr_maximum_age_bars, current_index=current_index, tolerance=atr_value * 0.05)
    cluster_target = resistance_cluster["level"] if direction > 0 and resistance_cluster and resistance_cluster["level"] > entry else support_cluster["level"] if direction < 0 and support_cluster and support_cluster["level"] < entry else None
    primary: list[dict[str, Any]] = []
    for item in (
        _candidate(cluster_target, "opposing_sr_cluster", 24),
        _candidate(first_pivot[1] if first_pivot else None, "nearest_confirmed_pivot", 16),
        _candidate(float(zone["proximal"]) if zone and ((direction > 0 and zone.get("kind") == "supply") or (direction < 0 and zone.get("kind") == "demand")) else None, "opposing_supply_demand_zone", 12),
        _candidate(range_high if direction > 0 else range_low, "range_boundary", 5),
        _candidate(entry + direction * target_basis, "adaptive_1r", 1),
    ):
        if item and direction * (item["price"] - entry) > 0:
            primary.append(item)
    hard = [item for item in primary if item["source"] in {"opposing_sr_cluster", "nearest_confirmed_pivot"}]
    cluster_hard = next((item for item in hard if item["source"] == "opposing_sr_cluster"), None)
    pivot_hard = next((item for item in hard if item["source"] == "nearest_confirmed_pivot"), None)
    if cluster_hard and pivot_hard and abs(cluster_hard["price"] - entry) <= abs(pivot_hard["price"] - entry) + atr_value * 0.10:
        nearest_hard = cluster_hard
    else:
        nearest_hard = min(hard, key=lambda item: abs(item["price"] - entry), default=None)
    first: dict[str, Any] | None = None
    if nearest_hard and abs(nearest_hard["price"] - entry) / risk >= params.short_plan_min_r:
        first = nearest_hard
    if first is None:
        valid_primary = [item for item in primary if abs(item["price"] - entry) / risk >= params.minimum_t1_r]
        if nearest_hard:
            hard_distance = abs(nearest_hard["price"] - entry)
            valid_primary = [item for item in valid_primary if abs(item["price"] - entry) <= hard_distance + atr_value * 0.05]
        first = min(valid_primary, key=lambda item: (abs(item["price"] - entry), -item["priority"]), default=None)
    if first is None:
        return {"valid": False, "reason": "insufficient_room_before_first_obstacle", "entry": entry, "stop": stop, "risk_atr": risk_atr, "stop_source": stop_source, "target_count": 0}
    targets = [first]
    used.append(first["price"])
    first_r = abs(first["price"] - entry) / risk
    short_plan = first_r < params.minimum_t1_r
    if not short_plan:
        for ordinal in (2, 3):
            pivot = _nearest_pivot(pivot_pool, price=entry, direction=direction, minimum_distance=abs(targets[-1]["price"] - entry) + min_distance, maximum_age_bars=params.sr_maximum_age_bars, current_index=current_index, exclude_prices=used, tolerance=atr_value * 0.10)
            fib = entry + direction * target_basis * float(ordinal)
            pivot_option = {"price": pivot[1], "source": f"new_confirmed_pivot_t{ordinal}", "priority": 16} if pivot and direction * (pivot[1] - targets[-1]["price"]) > min_distance else None
            fib_option = {"price": fib, "source": f"adaptive_{ordinal}r", "priority": 1} if direction * (fib - targets[-1]["price"]) > min_distance else None
            chosen = pivot_option or fib_option
            if chosen is None:
                chosen = {"price": targets[-1]["price"] + direction * target_basis, "source": f"adaptive_extension_t{ordinal}", "priority": 1}
            targets.append(chosen)
            used.append(chosen["price"])
    target_values = [item["price"] for item in targets]
    return {
        "valid": True,
        "entry": entry,
        "stop": stop,
        "targets": target_values,
        "target_sources": [item["source"] for item in targets],
        "target_count": len(target_values),
        "short_plan": short_plan,
        "risk": risk,
        "risk_atr": risk_atr,
        "target_basis_risk": target_basis,
        "first_rr": first_r,
        "stop_source": stop_source,
        "method": "cluster_then_pivot_then_secondary",
        "post_target1_trail": {"enabled": True, "length": 22, "atr_multiple": 3.0, "never_loosen": True},
    }


def _serialize_cluster(cluster: dict[str, Any] | None) -> dict[str, Any] | None:
    if cluster is None:
        return None
    return {**cluster, "level": _rounded(cluster.get("level")), "low": _rounded(cluster.get("low")), "high": _rounded(cluster.get("high")), "member_bars": list(cluster.get("member_bars") or ())}


def _serialize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    output = dict(plan)
    for key in ("entry", "stop", "risk", "target_basis_risk", "first_rr", "risk_atr"):
        if key in output and output[key] is not None:
            output[key] = _rounded(output[key])
    if "targets" in output:
        output["targets"] = [_rounded(value) for value in output.get("targets") or []]
    return output


def build_sc_feature_pack(
    frame: pd.DataFrame,
    interval: str = "1d",
    asset_class: str = "stock",
    market: str = "",
) -> dict[str, Any]:
    """Build the closed-candle SC-V92.5 decision contract without network I/O."""
    data = _prepare(frame)
    canonical = _interval(interval)
    params = _params(canonical)
    minimum = max(70, params.structure_lookback // 2)
    if len(data) < minimum:
        return {"ok": False, "version": SC_FEATURE_VERSION, "interval": canonical, "reason": "insufficient_closed_candles", "have": int(len(data)), "need": minimum}
    data = data.tail(max(params.structure_lookback + 80, 360)).copy()
    atr_value = _finite(_atr(data).iloc[-1]) or 0.0
    price = float(data["Close"].iloc[-1])
    if atr_value <= 0 or price <= 0:
        return {"ok": False, "version": SC_FEATURE_VERSION, "interval": canonical, "reason": "invalid_atr_or_price"}
    highs, lows = _pivots(data, params.pivot)
    if len(highs) < 2 or len(lows) < 2:
        return {"ok": False, "version": SC_FEATURE_VERSION, "interval": canonical, "reason": "missing_confirmed_pivots"}
    current_index = len(data) - 1
    recent_highs = [item for item in highs if item[0] >= len(data) - params.structure_lookback] or highs
    recent_lows = [item for item in lows if item[0] >= len(data) - params.structure_lookback] or lows
    last_high = recent_highs[-1][1]
    last_low = recent_lows[-1][1]
    structure_direction = 0
    structure_label = "neutral_structure"
    if recent_highs[-1][1] > recent_highs[-2][1] and recent_lows[-1][1] > recent_lows[-2][1]:
        structure_direction, structure_label = 1, "HH_HL"
    elif recent_highs[-1][1] < recent_highs[-2][1] and recent_lows[-1][1] < recent_lows[-2][1]:
        structure_direction, structure_label = -1, "LH_LL"
    sr_tolerance = max(atr_value * params.sr_tolerance_atr, price * 0.0005)
    support_cluster = _strong_cluster(lows, current_index=current_index, tolerance=sr_tolerance, minimum_touches=params.sr_minimum_touches, maximum_age_bars=params.sr_maximum_age_bars, stored=params.sr_stored_pivots, kind="support")
    resistance_cluster = _strong_cluster(highs, current_index=current_index, tolerance=sr_tolerance, minimum_touches=params.sr_minimum_touches, maximum_age_bars=params.sr_maximum_age_bars, stored=params.sr_stored_pivots, kind="resistance")
    event_contract = _event_contract(data, support_cluster=support_cluster, resistance_cluster=resistance_cluster, last_low=last_low, last_high=last_high, structure_direction=structure_direction, atr_value=atr_value, params=params)
    event = event_contract["selected"]
    direction = int(event["direction"] if event else structure_direction)
    veto = _opposition_veto(direction=direction, price=price, atr_value=atr_value, event=event, support_cluster=support_cluster, resistance_cluster=resistance_cluster)
    volume = _volume_context(data, asset_class=asset_class, market=market)
    evidence = _evidence(data, event=event, structure_direction=structure_direction, direction=direction, volume=volume, atr_value=atr_value, veto=veto, params=params)
    range_sample = data.iloc[-params.range_lookback - 1 : -1]
    range_high = float(range_sample["High"].max())
    range_low = float(range_sample["Low"].min())
    range_width = range_high - range_low
    zone = _compact_zone(data, direction, atr_value) if direction else None
    plan = _risk_plan(data, direction=direction, atr_value=atr_value, event=event, support_cluster=support_cluster, resistance_cluster=resistance_cluster, highs=highs, lows=lows, last_high=last_high, last_low=last_low, zone=zone, range_high=range_high, range_low=range_low, params=params, qualified=bool(evidence["qualified"]))
    qualified = bool(evidence["qualified"] and plan.get("valid"))
    reasons: list[str] = []
    warnings: list[str] = []
    if structure_direction:
        reasons.append(f"confirmed_pivot_structure:{structure_label}")
    if support_cluster:
        reasons.append(f"support_cluster:{support_cluster['touches']}_touches")
    if resistance_cluster:
        reasons.append(f"resistance_cluster:{resistance_cluster['touches']}_touches")
    if event:
        reasons.append(f"confirmed_event:{event['code']}")
    if volume["policy"] == "price_first":
        reasons.append("price_first_volume_policy")
    elif not evidence["participation"]:
        warnings.append("trusted_volume_did_not_confirm_participation")
    if veto["blocked"]:
        warnings.append(str(veto["reason"]))
    if event and not plan.get("valid"):
        warnings.append(str(plan.get("reason") or "invalid_risk_geometry"))
    event_output = dict(event) if event else {"code": "NONE", "direction": 0, "priority": 0, "level": None, "source": "", "trigger": ""}
    event_output["level"] = _rounded(event_output.get("level"))
    return {
        "ok": True,
        "version": SC_FEATURE_VERSION,
        "indicator_contract": "SC-V92.5/SC-FXM-V16",
        "accepted_sources": list(SC_INDICATOR_SOURCES),
        "interval": canonical,
        "asset_class": str(asset_class or ""),
        "market": str(market or ""),
        "closed_candles_only": True,
        "rows": int(len(data)),
        "price": _rounded(price),
        "atr": _rounded(atr_value),
        "direction": direction,
        "structure_direction": structure_direction,
        "structure": {"label": structure_label, "last_high": _rounded(last_high), "last_low": _rounded(last_low), "pivot_priority": 2},
        "event_direction": int(event_output.get("direction") or 0),
        "event_code": event_output.get("code"),
        "event": event_output,
        "event_candidates": [{**item, "level": _rounded(item.get("level"))} for item in event_contract["candidates"]],
        "priority_order": ["sr_cluster", "confirmed_pivot", "secondary_tools"],
        "sr": {"support": _serialize_cluster(support_cluster), "resistance": _serialize_cluster(resistance_cluster), "tolerance_atr": params.sr_tolerance_atr, "minimum_touches": params.sr_minimum_touches, "maximum_age_bars": params.sr_maximum_age_bars, "decision_priority": 1},
        "role_reversal": event_contract["role_reversal"],
        "opposition_veto": veto,
        "qualified": qualified,
        "confidence": max(0, min(100, int(evidence["score_percent"]))),
        "evidence": evidence,
        "evidence_axes": evidence["axes"],
        "volume": volume,
        "range": {"high": _rounded(range_high), "low": _rounded(range_low), "width": _rounded(range_width), "width_atr": round(range_width / atr_value, 4), "compressed": range_width <= atr_value * 2.5},
        "zone": ({key: _rounded(value) if key != "kind" else value for key, value in zone.items()} if zone else None),
        "risk_plan": _serialize_plan(plan),
        "higher_timeframe_policy": {"closed_bar_only": True, "pine_offset": 1, "automatic_override": False},
        "reasons": list(dict.fromkeys(reasons)),
        "warnings": list(dict.fromkeys(warnings)),
    }


__all__ = ["SC_FEATURE_VERSION", "SC_INDICATOR_SOURCES", "build_sc_feature_pack"]
