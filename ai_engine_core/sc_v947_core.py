"""Core data, pivots and current-role support/resistance for SC-V94.7."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Iterable
import pandas as pd

SC_FEATURE_VERSION = "94.7-PY"
SC_INDICATOR_CONTRACT = "SC-V94.7/SC-FXM-V18.8"
SC_INDICATOR_SOURCES = ("SC-V94.7-I", "SC-V94.7-D", "SC-FXM-V18.8")

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
    sr_stored_pivots: int = 60
    sr_minimum_touches: int = 2
    sr_tolerance_atr: float = 0.35
    sr_maximum_age_bars: int = 366
    break_buffer_atr: float = 0.05
    retest_tolerance_atr: float = 0.15
    stop_buffer_atr: float = 0.25
    evidence_minimum_percent: float = 55.0
    early_evidence_discount: float = 7.5

def _interval(value: Any) -> str:
    raw = str(value or "1d").strip().lower()
    return {
        "1min": "1m", "2min": "2m", "5min": "5m", "15min": "15m",
        "30min": "30m", "60m": "1h", "60min": "1h", "240m": "4h",
        "1wk": "1w", "week": "1w", "weekly": "1w",
        "month": "1mo", "monthly": "1mo",
    }.get(raw, raw)

def _params(interval: str) -> _Params:
    frame = _interval(interval)
    if frame in {"1m", "2m", "5m", "15m"}:
        return _Params(2, 180, 20, 10, 0.45, 1.80 if frame == "1m" else 2.20, sr_maximum_age_bars=720)
    if frame == "30m": return _Params(2, 220, 24, 8, 0.60, 2.40, sr_maximum_age_bars=720)
    if frame == "1h": return _Params(3, 260, 24, 8, 0.65, 2.70, sr_maximum_age_bars=720)
    if frame == "4h": return _Params(3, 300, 30, 8, 0.75, 3.10, sr_maximum_age_bars=540)
    if frame == "1d": return _Params(3, 366, 30, 8, 0.85, 3.50, sr_maximum_age_bars=366)
    if frame == "1w": return _Params(2, 220, 26, 6, 1.00, 4.00, sr_maximum_age_bars=156)
    if frame == "1mo": return _Params(2, 180, 24, 5, 1.10, 4.50, sr_maximum_age_bars=84)
    return _Params(3, 300, 26, 6, 0.85, 3.50, sr_maximum_age_bars=366)

def _finite(value: Any) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return number if math.isfinite(number) else None

def _rounded(value: Any) -> Any:
    number = _finite(value)
    return round(number, 8) if number is not None else None

def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty: return pd.DataFrame()
    aliases = {str(column).strip().lower(): column for column in frame.columns}
    rename = {aliases[wanted]: wanted.title() for wanted in ("open", "high", "low", "close", "volume") if wanted in aliases}
    output = frame.rename(columns=rename).copy(deep=True)
    required = ("Open", "High", "Low", "Close")
    if not all(column in output.columns for column in required): return pd.DataFrame()
    if "Volume" not in output.columns: output["Volume"] = 0.0
    for column in (*required, "Volume"): output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna(subset=list(required))
    valid = ((output["Open"] > 0) & (output["High"] > 0) & (output["Low"] > 0) & (output["Close"] > 0)
             & (output["High"] >= output[["Open", "Close"]].max(axis=1))
             & (output["Low"] <= output[["Open", "Close"]].min(axis=1))
             & (output["High"] >= output["Low"]) & (output["Volume"].fillna(0.0) >= 0))
    output = output.loc[valid]
    return output[~output.index.duplicated(keep="last")].sort_index()

def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["Close"].shift(1)
    true_range = pd.concat((frame["High"] - frame["Low"], (frame["High"] - previous).abs(), (frame["Low"] - previous).abs()), axis=1).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=min(period, 5)).mean()

def _pivots(frame: pd.DataFrame, width: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs, lows = [], []
    high_values, low_values = frame["High"].tolist(), frame["Low"].tolist()
    for index in range(width, len(frame) - width):
        if high_values[index] >= max(high_values[index-width:index+width+1]): highs.append((index, float(high_values[index])))
        if low_values[index] <= min(low_values[index-width:index+width+1]): lows.append((index, float(low_values[index])))
    return highs, lows

def _strong_cluster(pivots: list[tuple[int, float]], *, current_index: int, tolerance: float, minimum_touches: int, maximum_age_bars: int, stored: int, kind: str) -> dict[str, Any] | None:
    eligible = [item for item in pivots[-stored:] if 0 <= current_index - item[0] <= maximum_age_bars]
    selected = None
    for _, candidate_price in eligible:
        members = [item for item in eligible if abs(item[1] - candidate_price) <= tolerance]
        if len(members) < minimum_touches: continue
        prices, recent = [item[1] for item in members], max(item[0] for item in members)
        candidate = {"kind": kind, "origin_kind": kind, "level": sum(prices)/len(prices), "low": min(prices), "high": max(prices), "touches": len(members), "recent_bar": recent, "age_bars": current_index-recent, "member_bars": tuple(sorted(item[0] for item in members))}
        if selected is None or (candidate["touches"], candidate["recent_bar"]) > (selected["touches"], selected["recent_bar"]): selected = candidate
    return selected

def _cluster_candidates(pivots: list[tuple[int, float]], *, current_index: int, tolerance: float, minimum_touches: int, maximum_age_bars: int, stored: int, kind: str) -> list[dict[str, Any]]:
    eligible = [item for item in pivots[-stored:] if 0 <= current_index - item[0] <= maximum_age_bars]
    clusters, seen = [], set()
    for _, candidate_price in eligible:
        members = tuple(sorted(item for item in eligible if abs(item[1] - candidate_price) <= tolerance))
        if len(members) < minimum_touches: continue
        member_bars = tuple(item[0] for item in members)
        if member_bars in seen: continue
        seen.add(member_bars)
        prices, recent = [item[1] for item in members], max(member_bars)
        clusters.append({"kind": kind, "origin_kind": kind, "level": sum(prices)/len(prices), "low": min(prices), "high": max(prices), "touches": len(members), "recent_bar": recent, "age_bars": current_index-recent, "member_bars": member_bars})
    clusters.sort(key=lambda item: (float(item["level"]), -int(item["touches"]), -int(item["recent_bar"])))
    return clusters

def _current_role(cluster: dict[str, Any], *, price: float, tolerance: float) -> str:
    if price > float(cluster["high"]): return "support"
    if price < float(cluster["low"]): return "resistance"
    return "support" if str(cluster.get("origin_kind") or cluster.get("kind") or "") == "support" else "resistance"

def _role_distance(cluster: dict[str, Any], *, role: str, price: float) -> float:
    return max(0.0, price - float(cluster["high"])) if role == "support" else max(0.0, float(cluster["low"]) - price)

def _select_current_role_clusters(clusters: Iterable[dict[str, Any]], *, price: float, tolerance: float, atr_value: float, role: str, limit: int = 2) -> list[dict[str, Any]]:
    selected = []
    for source in clusters:
        if _current_role(source, price=price, tolerance=tolerance) != role: continue
        item = dict(source)
        item.update(kind=role, current_role=role, role_reversed=str(item.get("origin_kind")) != role)
        item["distance"] = _role_distance(item, role=role, price=price)
        item["distance_atr"] = item["distance"] / atr_value if atr_value > 0 else None
        if role == "support" and float(item["low"]) > price: continue
        if role == "resistance" and float(item["high"]) < price: continue
        selected.append(item)
    selected.sort(key=lambda item: (float(item["distance"]), -int(item.get("touches") or 0), int(item.get("age_bars") or 0)))
    return selected[:max(1, int(limit))]

def _resolve_current_role_overlap(supports: list[dict[str, Any]], resistances: list[dict[str, Any]], *, tolerance: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not supports or not resistances: return supports, resistances
    support, resistance = supports[0], resistances[0]
    overlap = float(support["high"]) >= float(resistance["low"]) - tolerance * 0.10 or float(support["level"]) >= float(resistance["level"])
    if not overlap: return supports, resistances
    support_rank = (int(support.get("touches") or 0), -int(support.get("age_bars") or 0))
    resistance_rank = (int(resistance.get("touches") or 0), -int(resistance.get("age_bars") or 0))
    if support_rank >= resistance_rank:
        return supports, [item for item in resistances if float(item["low"]) > float(support["high"]) + tolerance * 0.10]
    return [item for item in supports if float(item["high"]) < float(resistance["low"]) - tolerance * 0.10], resistances

def _select_origin_cluster(clusters: Iterable[dict[str, Any]], *, price: float) -> dict[str, Any] | None:
    return min(list(clusters), key=lambda item: (abs(float(item["level"])-price), -int(item.get("touches") or 0), int(item.get("age_bars") or 0)), default=None)

def _nearest_pivot(pivots: Iterable[tuple[int, float]], *, price: float, direction: int, minimum_distance: float, maximum_age_bars: int, current_index: int, exclude_prices: Iterable[float] = (), tolerance: float = 0.0) -> tuple[int, float] | None:
    excluded, candidates = tuple(float(value) for value in exclude_prices), []
    for index, level in pivots:
        if current_index-index > maximum_age_bars: continue
        if direction > 0 and level < price+minimum_distance: continue
        if direction < 0 and level > price-minimum_distance: continue
        if any(abs(level-used) <= tolerance for used in excluded): continue
        candidates.append((abs(level-price), index, level))
    if not candidates: return None
    _, index, level = min(candidates, key=lambda item: (item[0], -item[1]))
    return index, level

def _serialize_cluster(cluster: dict[str, Any] | None) -> dict[str, Any] | None:
    if cluster is None: return None
    output = dict(cluster)
    for key in ("level", "low", "high", "distance", "distance_atr"):
        if key in output: output[key] = _rounded(output.get(key))
    output["member_bars"] = list(cluster.get("member_bars") or ())
    return output

def classify_current_role_levels(frame: pd.DataFrame, interval: str = "1d", *, max_levels: int = 6, lookback: int | None = None) -> dict[str, Any]:
    data, canonical = _prepare(frame), _interval(interval)
    params = _params(canonical)
    if lookback is not None and lookback > 0: data = data.tail(int(lookback)).copy()
    if len(data) < max(30, params.pivot*2+10): return {"ok": False, "support": [], "resistance": [], "reason": "insufficient_closed_candles"}
    atr_value, price = _finite(_atr(data).iloc[-1]) or 0.0, _finite(data["Close"].iloc[-1]) or 0.0
    if atr_value <= 0 or price <= 0: return {"ok": False, "support": [], "resistance": [], "reason": "invalid_atr_or_price"}
    highs, lows = _pivots(data, params.pivot)
    current_index, tolerance = len(data)-1, max(atr_value*params.sr_tolerance_atr, price*0.0005)
    clusters = [*_cluster_candidates(lows, current_index=current_index, tolerance=tolerance, minimum_touches=params.sr_minimum_touches, maximum_age_bars=min(params.sr_maximum_age_bars, len(data)), stored=params.sr_stored_pivots, kind="support"), *_cluster_candidates(highs, current_index=current_index, tolerance=tolerance, minimum_touches=params.sr_minimum_touches, maximum_age_bars=min(params.sr_maximum_age_bars, len(data)), stored=params.sr_stored_pivots, kind="resistance")]
    supports = _select_current_role_clusters(clusters, price=price, tolerance=tolerance, atr_value=atr_value, role="support", limit=max_levels)
    resistances = _select_current_role_clusters(clusters, price=price, tolerance=tolerance, atr_value=atr_value, role="resistance", limit=max_levels)
    if not supports:
        piv = sorted(({"level": level, "bar": index} for index, level in lows if level < price), key=lambda item: (price-float(item["level"]), -int(item["bar"])))
        supports = [{"kind":"support","current_role":"support","origin_kind":"support","role_reversed":False,"level":i["level"],"low":i["level"],"high":i["level"],"touches":1,"recent_bar":i["bar"],"age_bars":current_index-i["bar"],"member_bars":(i["bar"],),"distance":price-i["level"],"distance_atr":(price-i["level"])/atr_value} for i in piv[:max_levels]]
    if not resistances:
        piv = sorted(({"level": level, "bar": index} for index, level in highs if level > price), key=lambda item: (float(item["level"])-price, -int(item["bar"])))
        resistances = [{"kind":"resistance","current_role":"resistance","origin_kind":"resistance","role_reversed":False,"level":i["level"],"low":i["level"],"high":i["level"],"touches":1,"recent_bar":i["bar"],"age_bars":current_index-i["bar"],"member_bars":(i["bar"],),"distance":i["level"]-price,"distance_atr":(i["level"]-price)/atr_value} for i in piv[:max_levels]]
    supports, resistances = _resolve_current_role_overlap(supports, resistances, tolerance=tolerance)
    return {"ok": True, "price": price, "atr": atr_value, "tolerance": tolerance, "support": [_serialize_cluster(i) for i in supports], "resistance": [_serialize_cluster(i) for i in resistances], "classification": "current_role_relative_to_closed_price"}

__all__ = [name for name in globals() if name.startswith("_") or name.startswith("SC_") or name == "classify_current_role_levels"]
