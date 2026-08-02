"""Closed-candle signal, role-reversal and evidence logic for SC-V94.7."""
from __future__ import annotations
from typing import Any
import pandas as pd
from .sc_v947_core import _Params


def _compact_zone(frame: pd.DataFrame, direction: int, atr_value: float) -> dict[str, Any] | None:
    sample = frame.iloc[-14:-1]
    if sample.empty: return None
    spread = (sample["High"] - sample["Low"]).replace(0.0, pd.NA)
    body = (sample["Close"] - sample["Open"]).abs()
    base = (body / spread).fillna(1.0) <= 0.50
    opposite = sample["Close"] < sample["Open"] if direction > 0 else sample["Close"] > sample["Open"]
    candidates = sample.loc[base | opposite]
    if candidates.empty: return None
    anchor = candidates.iloc[-1]
    body_high, body_low = max(float(anchor["Open"]), float(anchor["Close"])), min(float(anchor["Open"]), float(anchor["Close"]))
    proximal, distal, kind = (body_high, float(anchor["Low"]), "demand") if direction > 0 else (body_low, float(anchor["High"]), "supply")
    width = abs(proximal - distal)
    if width <= 0 or width > max(atr_value * 2.5, abs(proximal) * 0.08): return None
    return {"kind": kind, "proximal": proximal, "distal": distal, "width_atr": width / atr_value}


def _volume_policy(asset_class: str, market: str) -> str:
    asset, market_text = str(asset_class or "").lower(), str(market or "").upper()
    if asset in {"stock", "fund", "dr", "crypto", "future", "futures"}: return "required"
    if asset in {"forex", "index", "cfd", "bond", "commodity", "spot"}: return "price_first"
    return "required" if market_text in {"SAUDI", "US", "US_OPTIONS", "CRYPTO"} else "price_first"


def _volume_context(frame: pd.DataFrame, *, asset_class: str, market: str) -> dict[str, Any]:
    policy = _volume_policy(asset_class, market)
    volumes = frame["Volume"].clip(lower=0.0)
    positive = volumes.iloc[-31:-1]
    positive = positive[positive > 0]
    baseline = float(positive.median()) if len(positive) >= 10 else 0.0
    current, ratio = float(volumes.iloc[-1]), None
    if baseline > 0: ratio = current / baseline
    bar = frame.iloc[-1]
    spread = max(float(bar["High"] - bar["Low"]), 1e-12)
    result = abs(float(bar["Close"] - bar["Open"])) / spread
    effort = "high_effort_low_result" if ratio is not None and ratio >= 1.5 and result <= .35 else "high_effort_high_result" if ratio is not None and ratio >= 1.2 and result >= .60 else "normal"
    return {"policy": policy, "trusted": policy == "required" and ratio is not None, "ratio": round(ratio, 4) if ratio is not None else None, "participation": bool(ratio is not None and ratio >= 1.10), "quiet": bool(ratio is not None and ratio <= 1.0), "effort_result": effort, "method": "closed_bar_median_30"}


def _trend_context(frame: pd.DataFrame, atr_value: float) -> dict[str, Any]:
    close = frame["Close"]
    fast, slow = close.ewm(span=20, adjust=False).mean(), close.ewm(span=50, adjust=False).mean()
    macro = close.ewm(span=min(200, max(60, len(frame)//2)), adjust=False).mean()
    fv, sv, mv = float(fast.iloc[-1]), float(slow.iloc[-1]), float(macro.iloc[-1])
    direction = 1 if fv > sv and close.iloc[-1] > mv else -1 if fv < sv and close.iloc[-1] < mv else 0
    slope = (fv - float(fast.iloc[-4])) / atr_value if len(fast) >= 4 and atr_value > 0 else 0.0
    return {"direction": direction, "fast": fv, "slow": sv, "macro": mv, "slope_atr": slope, "aligned": direction != 0, "method": "ema20_50_structural_horizon"}


def _fvg_context(frame: pd.DataFrame, atr_value: float, lookback: int = 8) -> dict[str, Any]:
    bullish, bearish = [], []
    for index in range(max(2, len(frame)-lookback), len(frame)):
        ph, pl = float(frame["High"].iloc[index-2]), float(frame["Low"].iloc[index-2])
        low, high = float(frame["Low"].iloc[index]), float(frame["High"].iloc[index])
        if low > ph: bullish.append({"bar": index, "low": ph, "high": low})
        if high < pl: bearish.append({"bar": index, "low": high, "high": pl})
    close = float(frame["Close"].iloc[-1])
    nearest = lambda values: min(values, key=lambda item: abs((float(item["low"])+float(item["high"]))/2-close), default=None)
    return {"bullish": nearest(bullish), "bearish": nearest(bearish), "bullish_count": len(bullish), "bearish_count": len(bearish), "maximum_distance_atr": 3.0, "atr": atr_value}


def _range_wyckoff_context(frame: pd.DataFrame, *, lookback: int, atr_value: float) -> dict[str, Any]:
    prior = frame.iloc[-lookback-1:-1]
    if prior.empty: return {}
    rh, rl = float(prior["High"].max()), float(prior["Low"].min())
    close, high, low = float(frame["Close"].iloc[-1]), float(frame["High"].iloc[-1]), float(frame["Low"].iloc[-1])
    width = rh - rl
    spring, upthrust = low < rl - atr_value*.05 and close > rl, high > rh + atr_value*.05 and close < rh
    return {"high": rh, "low": rl, "width": width, "width_atr": width/atr_value if atr_value > 0 else None, "compressed": width <= atr_value*2.5, "spring": spring, "upthrust": upthrust, "state": "spring" if spring else "upthrust" if upthrust else "range"}


def _role_state(frame: pd.DataFrame, cluster: dict[str, Any] | None, *, direction: int, buffer: float, retest_window: int, tolerance: float) -> dict[str, Any]:
    if cluster is None or len(frame) < retest_window + 2: return {"broken_recently": False, "retest": False, "failed": False, "break_bar": None}
    closes, highs, lows = frame["Close"].tolist(), frame["High"].tolist(), frame["Low"].tolist()
    break_bar = None
    for index in range(max(1, len(frame)-retest_window-1), len(frame)-1):
        crossed = closes[index-1] <= cluster["high"]+buffer and closes[index] > cluster["high"]+buffer if direction > 0 else closes[index-1] >= cluster["low"]-buffer and closes[index] < cluster["low"]-buffer
        if crossed: break_bar = index
    current = closes[-1]
    if direction > 0:
        retest = break_bar is not None and lows[-1] <= cluster["high"]+tolerance and current > cluster["high"]
        failed = break_bar is not None and current < cluster["low"]-buffer
    else:
        retest = break_bar is not None and highs[-1] >= cluster["low"]-tolerance and current < cluster["low"]
        failed = break_bar is not None and current > cluster["high"]+buffer
    return {"broken_recently": break_bar is not None, "retest": bool(retest and not failed), "failed": bool(failed), "break_bar": break_bar}


def _event_contract(frame: pd.DataFrame, *, support_cluster: dict[str, Any] | None, resistance_cluster: dict[str, Any] | None, last_low: float, last_high: float, structure_direction: int, atr_value: float, params: _Params) -> dict[str, Any]:
    prev, close, high, low, open_value = map(float, (frame["Close"].iloc[-2], frame["Close"].iloc[-1], frame["High"].iloc[-1], frame["Low"].iloc[-1], frame["Open"].iloc[-1]))
    buffer, tolerance = max(params.break_buffer_atr*atr_value, close*.0005), max(params.retest_tolerance_atr*atr_value, close*.001)
    bull = _role_state(frame, resistance_cluster, direction=1, buffer=buffer, retest_window=params.retest_window, tolerance=tolerance)
    bear = _role_state(frame, support_cluster, direction=-1, buffer=buffer, retest_window=params.retest_window, tolerance=tolerance)
    events = []
    def add(code, direction, priority, level, source, trigger): events.append({"code": code, "direction": direction, "priority": priority, "level": level, "source": source, "trigger": trigger})
    if resistance_cluster:
        break_up = prev <= resistance_cluster["high"]+buffer and close > resistance_cluster["high"]+buffer
        fakeout = high > resistance_cluster["high"]+buffer and close <= resistance_cluster["high"]
        if bull["retest"]: add("CLUSTER_RETEST_UP", 1, 340, resistance_cluster["level"], "sr_cluster", "confirmed_role_reversal")
        elif fakeout: add("CLUSTER_FAKEOUT_DOWN", -1, 330, resistance_cluster["level"], "sr_cluster", "confirmed_close_return")
        elif break_up: add("CLUSTER_CHOCH_UP" if structure_direction < 0 else "CLUSTER_BOS_UP", 1, 240, resistance_cluster["high"], "sr_cluster", "confirmed_close_break")
    if support_cluster:
        break_down = prev >= support_cluster["low"]-buffer and close < support_cluster["low"]-buffer
        fakeout = low < support_cluster["low"]-buffer and close >= support_cluster["low"]
        if bear["retest"]: add("CLUSTER_RETEST_DOWN", -1, 340, support_cluster["level"], "sr_cluster", "confirmed_role_reversal")
        elif fakeout: add("CLUSTER_FAKEOUT_UP", 1, 330, support_cluster["level"], "sr_cluster", "confirmed_close_return")
        elif break_down: add("CLUSTER_CHOCH_DOWN" if structure_direction > 0 else "CLUSTER_BOS_DOWN", -1, 240, support_cluster["low"], "sr_cluster", "confirmed_close_break")
    prior = frame.iloc[-params.retest_window-1:-1]
    if bool((prior["Close"] > last_high+buffer).any()) and low <= last_high+tolerance and close > last_high: add("PIVOT_RETEST_UP", 1, 300, last_high, "pivot", "confirmed_role_reversal")
    if bool((prior["Close"] < last_low-buffer).any()) and high >= last_low-tolerance and close < last_low: add("PIVOT_RETEST_DOWN", -1, 300, last_low, "pivot", "confirmed_role_reversal")
    if prev <= last_high+buffer and close > last_high+buffer: add("PIVOT_CHOCH_UP" if structure_direction < 0 else "PIVOT_BOS_UP", 1, 200, last_high, "pivot", "confirmed_close_break")
    if prev >= last_low-buffer and close < last_low-buffer: add("PIVOT_CHOCH_DOWN" if structure_direction > 0 else "PIVOT_BOS_DOWN", -1, 200, last_low, "pivot", "confirmed_close_break")
    location_low, location_high = (support_cluster["low"] if support_cluster else last_low), (resistance_cluster["high"] if resistance_cluster else last_high)
    if low < location_low-buffer and close > location_low and close > open_value: add("EARLY_SWEEP_UP", 1, 100, location_low, "sr_cluster" if support_cluster else "pivot", "confirmed_recovery_close")
    if high > location_high+buffer and close < location_high and close < open_value: add("EARLY_SWEEP_DOWN", -1, 100, location_high, "sr_cluster" if resistance_cluster else "pivot", "confirmed_recovery_close")
    return {"selected": max(events, key=lambda item: item["priority"], default=None), "candidates": sorted(events, key=lambda item: item["priority"], reverse=True), "buffer": buffer, "tolerance": tolerance, "role_reversal": {"bullish": bull, "bearish": bear}}


def _opposition_veto(*, direction: int, price: float, atr_value: float, event: dict[str, Any] | None, support_cluster: dict[str, Any] | None, resistance_cluster: dict[str, Any] | None) -> dict[str, Any]:
    empty = {"blocked": False, "side": "", "distance_atr": None, "reason": ""}
    if direction > 0 and resistance_cluster:
        if float(resistance_cluster["high"]) < price-.15*atr_value: return empty
        distance = float(resistance_cluster["low"])-price
        broken = bool(event and event["direction"] > 0 and event["source"] == "sr_cluster" and event["trigger"] == "confirmed_close_break")
        blocked = -.15*atr_value <= distance <= atr_value and not broken and not (event and event["code"] == "CLUSTER_RETEST_UP")
        return {"blocked": blocked, "side": "resistance", "distance_atr": distance/atr_value, "reason": "active_resistance_cluster_opposes_long" if blocked else ""}
    if direction < 0 and support_cluster:
        if float(support_cluster["low"]) > price+.15*atr_value: return empty
        distance = price-float(support_cluster["high"])
        broken = bool(event and event["direction"] < 0 and event["source"] == "sr_cluster" and event["trigger"] == "confirmed_close_break")
        blocked = -.15*atr_value <= distance <= atr_value and not broken and not (event and event["code"] == "CLUSTER_RETEST_DOWN")
        return {"blocked": blocked, "side": "support", "distance_atr": distance/atr_value, "reason": "active_support_cluster_opposes_short" if blocked else ""}
    return empty


def _evidence(frame: pd.DataFrame, *, event: dict[str, Any] | None, structure_direction: int, direction: int, volume: dict[str, Any], atr_value: float, veto: dict[str, Any], params: _Params, trend_direction: int = 0, wyckoff_state: str = "range") -> dict[str, Any]:
    bar = frame.iloc[-1]
    spread = max(float(bar["High"]-bar["Low"]), 1e-12)
    body_ratio = abs(float(bar["Close"]-bar["Open"]))/spread
    close_location = (float(bar["Close"])-float(bar["Low"]))/spread
    displacement = spread/atr_value
    participation = bool(volume["participation"] or (body_ratio >= .60 and displacement >= 1.0))
    volume_pass = volume["policy"] != "required" or participation
    structure_support = bool(direction and (structure_direction == direction or (event and "CHOCH" in event["code"])))
    trend_support = bool(direction and trend_direction in {0, direction})
    location_support = bool(event and event["source"] in {"sr_cluster", "pivot"})
    wyckoff_support = (direction > 0 and wyckoff_state == "spring") or (direction < 0 and wyckoff_state == "upthrust")
    axes = {"structure": 78 if structure_support else 36 if direction else 20, "trend": 72 if trend_support else 30, "participation": 76 if volume_pass else 28, "location": 90 if event and event["source"] == "sr_cluster" else 76 if location_support else 35, "trigger": 94 if event and event["priority"] >= 300 else 86 if event and event["priority"] >= 200 else 76 if wyckoff_support else 72 if event else 20}
    own = sum(value >= 60 for value in axes.values())
    opposition = int(bool(veto.get("blocked"))) + int(structure_direction == -direction and not (event and "CHOCH" in event["code"])) + int(trend_direction == -direction)
    score = round(sum(axes.values())/len(axes))
    direct = bool(event and event["priority"] in {200, 240})
    close_quality = close_location >= .72 if direction > 0 else close_location <= .28
    direct_quality = bool(not direct or (body_ratio >= .55 and close_quality and volume_pass and own >= 2 and own >= opposition+2))
    threshold = params.evidence_minimum_percent - (params.early_evidence_discount if event and event["priority"] == 100 else 0.0)
    exceptional = bool(event and event["priority"] >= 300 and axes["trigger"] >= 90 and axes["location"] >= 76)
    qualified = bool(event and not veto.get("blocked") and direct_quality and score >= threshold and (own >= 2 or exceptional) and own > opposition)
    return {"axes": axes, "own_count": own, "opposition_count": opposition, "score_percent": score, "minimum_percent": threshold, "qualified": qualified, "exceptional_single_trigger": exceptional, "direct_break_quality": direct_quality, "body_ratio": round(body_ratio,4), "close_location": round(close_location,4), "displacement_atr": round(displacement,4), "participation": participation}


__all__ = [name for name in globals() if name.startswith("_")]
