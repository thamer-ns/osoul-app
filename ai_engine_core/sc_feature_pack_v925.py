"""Closed-candle SC-V94.7 / SC-FXM-V18.8 analysis contract.

The public filename remains stable for deployed imports. Horizontal levels are
classified by current role relative to the latest completed close.
"""
from __future__ import annotations
from typing import Any
import pandas as pd
from .sc_v947_core import *
from .sc_v947_signals import *
from .sc_v947_plan import *


def build_sc_feature_pack(frame: pd.DataFrame, interval: str = "1d", asset_class: str = "stock", market: str = "") -> dict[str, Any]:
    """Build the deterministic SC-V94.7 contract without network I/O."""
    data, canonical = _prepare(frame), _interval(interval)
    params = _params(canonical)
    minimum = max(70, params.structure_lookback // 2)
    if len(data) < minimum:
        return {"ok": False, "version": SC_FEATURE_VERSION, "indicator_contract": SC_INDICATOR_CONTRACT, "interval": canonical, "reason": "insufficient_closed_candles", "have": int(len(data)), "need": minimum}
    data = data.tail(max(params.structure_lookback+80, params.sr_maximum_age_bars+params.pivot*2+10, 360)).copy()
    atr_value, price = _finite(_atr(data).iloc[-1]) or 0.0, float(data["Close"].iloc[-1])
    if atr_value <= 0 or price <= 0:
        return {"ok": False, "version": SC_FEATURE_VERSION, "indicator_contract": SC_INDICATOR_CONTRACT, "interval": canonical, "reason": "invalid_atr_or_price"}
    highs, lows = _pivots(data, params.pivot)
    if len(highs) < 2 or len(lows) < 2:
        return {"ok": False, "version": SC_FEATURE_VERSION, "indicator_contract": SC_INDICATOR_CONTRACT, "interval": canonical, "reason": "missing_confirmed_pivots"}
    current_index = len(data)-1
    recent_highs = [item for item in highs if item[0] >= len(data)-params.structure_lookback] or highs
    recent_lows = [item for item in lows if item[0] >= len(data)-params.structure_lookback] or lows
    last_high, last_low = recent_highs[-1][1], recent_lows[-1][1]
    structure_direction, structure_label = 0, "neutral_structure"
    if recent_highs[-1][1] > recent_highs[-2][1] and recent_lows[-1][1] > recent_lows[-2][1]: structure_direction, structure_label = 1, "HH_HL"
    elif recent_highs[-1][1] < recent_highs[-2][1] and recent_lows[-1][1] < recent_lows[-2][1]: structure_direction, structure_label = -1, "LH_LL"

    sr_tolerance = max(atr_value*params.sr_tolerance_atr, price*.0005)
    low_clusters = _cluster_candidates(lows, current_index=current_index, tolerance=sr_tolerance, minimum_touches=params.sr_minimum_touches, maximum_age_bars=params.sr_maximum_age_bars, stored=params.sr_stored_pivots, kind="support")
    high_clusters = _cluster_candidates(highs, current_index=current_index, tolerance=sr_tolerance, minimum_touches=params.sr_minimum_touches, maximum_age_bars=params.sr_maximum_age_bars, stored=params.sr_stored_pivots, kind="resistance")
    all_clusters = [*low_clusters, *high_clusters]
    current_supports = _select_current_role_clusters(all_clusters, price=price, tolerance=sr_tolerance, atr_value=atr_value, role="support", limit=8)
    current_resistances = _select_current_role_clusters(all_clusters, price=price, tolerance=sr_tolerance, atr_value=atr_value, role="resistance", limit=8)
    current_supports, current_resistances = _resolve_current_role_overlap(current_supports, current_resistances, tolerance=sr_tolerance)
    support_cluster = current_supports[0] if current_supports else None
    resistance_cluster = current_resistances[0] if current_resistances else None

    event_support_origin = _select_origin_cluster(low_clusters, price=price)
    event_resistance_origin = _select_origin_cluster(high_clusters, price=price)
    event_contract = _event_contract(data, support_cluster=event_support_origin, resistance_cluster=event_resistance_origin, last_low=last_low, last_high=last_high, structure_direction=structure_direction, atr_value=atr_value, params=params)
    event = event_contract["selected"]
    direction = int(event["direction"] if event else structure_direction)
    veto = _opposition_veto(direction=direction, price=price, atr_value=atr_value, event=event, support_cluster=support_cluster, resistance_cluster=resistance_cluster)
    volume = _volume_context(data, asset_class=asset_class, market=market)
    trend = _trend_context(data, atr_value)
    wyckoff = _range_wyckoff_context(data, lookback=params.range_lookback, atr_value=atr_value)
    evidence = _evidence(data, event=event, structure_direction=structure_direction, direction=direction, volume=volume, atr_value=atr_value, veto=veto, params=params, trend_direction=int(trend.get("direction") or 0), wyckoff_state=str(wyckoff.get("state") or "range"))
    range_high = float(wyckoff.get("high") or data["High"].iloc[-params.range_lookback-1:-1].max())
    range_low = float(wyckoff.get("low") or data["Low"].iloc[-params.range_lookback-1:-1].min())
    range_width = range_high-range_low
    demand_zone, supply_zone = _compact_zone(data, 1, atr_value), _compact_zone(data, -1, atr_value)
    active_zone = demand_zone if direction > 0 else supply_zone if direction < 0 else None
    opposing_zone = supply_zone if direction > 0 else demand_zone if direction < 0 else None
    plan = _risk_plan(data, direction=direction, atr_value=atr_value, event=event, support_cluster=support_cluster, resistance_cluster=resistance_cluster, highs=highs, lows=lows, last_high=last_high, last_low=last_low, zone=opposing_zone or active_zone, range_high=range_high, range_low=range_low, params=params, qualified=bool(evidence["qualified"]))
    integrity = _integrity(price=price, support=support_cluster, resistance=resistance_cluster, plan=plan)
    qualified = bool(evidence["qualified"] and plan.get("valid") and integrity.get("ok"))
    reasons, warnings = [], []
    if structure_direction: reasons.append(f"confirmed_pivot_structure:{structure_label}")
    if support_cluster: reasons.append(f"current_support_cluster:{support_cluster['touches']}_touches" + (":role_reversed" if support_cluster.get("role_reversed") else ""))
    if resistance_cluster: reasons.append(f"current_resistance_cluster:{resistance_cluster['touches']}_touches" + (":role_reversed" if resistance_cluster.get("role_reversed") else ""))
    if event: reasons.append(f"confirmed_event:{event['code']}")
    if wyckoff.get("spring"): reasons.append("wyckoff_spring_confirmed_on_close")
    if wyckoff.get("upthrust"): reasons.append("wyckoff_upthrust_confirmed_on_close")
    if volume["policy"] == "price_first": reasons.append("price_first_volume_policy")
    elif not evidence["participation"]: warnings.append("trusted_volume_did_not_confirm_participation")
    if veto["blocked"]: warnings.append(str(veto["reason"]))
    if event and not plan.get("valid"): warnings.append(str(plan.get("reason") or "invalid_risk_geometry"))
    warnings.extend(str(item) for item in integrity.get("issues") or [])
    event_output = dict(event) if event else {"code":"NONE","direction":0,"priority":0,"level":None,"source":"","trigger":""}
    event_output["level"] = _rounded(event_output.get("level"))
    fvg = _fvg_context(data, atr_value)
    return {
        "ok": True, "version": SC_FEATURE_VERSION, "indicator_contract": SC_INDICATOR_CONTRACT,
        "accepted_sources": list(SC_INDICATOR_SOURCES), "interval": canonical,
        "asset_class": str(asset_class or ""), "market": str(market or ""),
        "closed_candles_only": True, "rows": int(len(data)), "price": _rounded(price), "atr": _rounded(atr_value),
        "direction": direction, "structure_direction": structure_direction,
        "structure": {"label": structure_label, "last_high": _rounded(last_high), "last_low": _rounded(last_low), "pivot_priority": 2},
        "trend": _serialize_numeric_mapping(trend), "event_direction": int(event_output.get("direction") or 0),
        "event_code": event_output.get("code"), "event": event_output,
        "event_candidates": [{**item, "level": _rounded(item.get("level"))} for item in event_contract["candidates"]],
        "priority_order": ["current_role_sr_cluster", "confirmed_pivot", "secondary_tools"],
        "sr": {"support": _serialize_cluster(support_cluster), "resistance": _serialize_cluster(resistance_cluster),
               "next_support": _serialize_cluster(current_supports[1] if len(current_supports)>1 else None),
               "next_resistance": _serialize_cluster(current_resistances[1] if len(current_resistances)>1 else None),
               "origin_support": _serialize_cluster(event_support_origin), "origin_resistance": _serialize_cluster(event_resistance_origin),
               "tolerance_atr": params.sr_tolerance_atr, "minimum_touches": params.sr_minimum_touches,
               "maximum_age_bars": params.sr_maximum_age_bars, "decision_priority": 1,
               "classification": "current_role_relative_to_closed_price"},
        "role_reversal": event_contract["role_reversal"], "opposition_veto": veto,
        "qualified": qualified, "confidence": max(0, min(100, int(evidence["score_percent"]))),
        "evidence": evidence, "evidence_axes": evidence["axes"], "volume": volume,
        "range": {"high": _rounded(range_high), "low": _rounded(range_low), "width": _rounded(range_width), "width_atr": round(range_width/atr_value,4), "compressed": range_width <= atr_value*2.5},
        "wyckoff": _serialize_numeric_mapping(wyckoff),
        "zones": {"demand": _serialize_numeric_mapping(demand_zone), "supply": _serialize_numeric_mapping(supply_zone)},
        "zone": _serialize_numeric_mapping(active_zone), "fvg": _serialize_numeric_mapping(fvg),
        "risk_plan": _serialize_plan(plan),
        "higher_timeframe_policy": {"closed_bar_only": True, "pine_offset": 1, "automatic_override": False, "current_series_macro_proxy": True},
        "integrity": integrity, "reasons": list(dict.fromkeys(reasons)), "warnings": list(dict.fromkeys(warnings)),
    }


__all__ = ["SC_FEATURE_VERSION", "SC_INDICATOR_CONTRACT", "SC_INDICATOR_SOURCES", "build_sc_feature_pack", "classify_current_role_levels"]
