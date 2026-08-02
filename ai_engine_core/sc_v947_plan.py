"""Direction-safe stops and targets for SC-V94.7."""
from __future__ import annotations
import math
from typing import Any
import pandas as pd
from .sc_v947_core import _Params, _finite, _nearest_pivot, _rounded


def _candidate(price: float | None, source: str, priority: int) -> dict[str, Any] | None:
    value = _finite(price)
    if value is None or value <= 0: return None
    return {"price": value, "source": source, "priority": priority}


def _risk_plan(frame: pd.DataFrame, *, direction: int, atr_value: float, event: dict[str, Any] | None, support_cluster: dict[str, Any] | None, resistance_cluster: dict[str, Any] | None, highs: list[tuple[int, float]], lows: list[tuple[int, float]], last_high: float, last_low: float, zone: dict[str, Any] | None, range_high: float, range_low: float, params: _Params, qualified: bool) -> dict[str, Any]:
    if direction not in {-1, 1} or event is None or not qualified:
        return {"valid": False, "reason": "no_qualified_confirmed_trigger", "target_count": 0}
    entry, current_index = float(frame["Close"].iloc[-1]), len(frame)-1
    stop_buffer, stop_source, protective = atr_value*params.stop_buffer_atr, "", None
    if direction > 0:
        if support_cluster and float(support_cluster["high"]) < entry: protective, stop_source = float(support_cluster["low"]), "protective_support_cluster"
        elif last_low < entry: protective, stop_source = last_low, "confirmed_pivot_low"
        elif zone and zone.get("kind") == "demand": protective, stop_source = float(zone["distal"]), "demand_zone"
        stop = protective-stop_buffer if protective is not None else None
    else:
        if resistance_cluster and float(resistance_cluster["low"]) > entry: protective, stop_source = float(resistance_cluster["high"]), "protective_resistance_cluster"
        elif last_high > entry: protective, stop_source = last_high, "confirmed_pivot_high"
        elif zone and zone.get("kind") == "supply": protective, stop_source = float(zone["distal"]), "supply_zone"
        stop = protective+stop_buffer if protective is not None else None
    if stop is None: return {"valid": False, "reason": "missing_structural_invalidation", "target_count": 0}
    risk = entry-stop if direction > 0 else stop-entry
    if not math.isfinite(risk) or risk <= 0: return {"valid": False, "reason": "invalid_stop_geometry", "target_count": 0}
    risk_atr = risk/atr_value
    if risk_atr > params.max_risk_atr: return {"valid": False, "reason": "stop_too_far", "risk_atr": risk_atr, "stop_source": stop_source, "target_count": 0}
    target_basis, min_distance = max(risk, atr_value*params.min_risk_atr), max(atr_value*.05, entry*.0005)
    pivot_pool, used = (highs if direction > 0 else lows), []
    first_pivot = _nearest_pivot(pivot_pool, price=entry, direction=direction, minimum_distance=min_distance, maximum_age_bars=params.sr_maximum_age_bars, current_index=current_index, tolerance=atr_value*.05)
    cluster_target = resistance_cluster["level"] if direction > 0 and resistance_cluster and resistance_cluster["level"] > entry else support_cluster["level"] if direction < 0 and support_cluster and support_cluster["level"] < entry else None
    primary = []
    for item in (_candidate(cluster_target, "opposing_sr_cluster", 24), _candidate(first_pivot[1] if first_pivot else None, "nearest_confirmed_pivot", 16), _candidate(float(zone["proximal"]) if zone and ((direction > 0 and zone.get("kind") == "supply") or (direction < 0 and zone.get("kind") == "demand")) else None, "opposing_supply_demand_zone", 12), _candidate(range_high if direction > 0 else range_low, "range_boundary", 5), _candidate(entry+direction*target_basis, "adaptive_1r", 1)):
        if item and direction*(item["price"]-entry) > 0: primary.append(item)
    hard = [item for item in primary if item["source"] in {"opposing_sr_cluster", "nearest_confirmed_pivot"}]
    cluster_hard = next((item for item in hard if item["source"] == "opposing_sr_cluster"), None)
    pivot_hard = next((item for item in hard if item["source"] == "nearest_confirmed_pivot"), None)
    nearest_hard = cluster_hard if cluster_hard and pivot_hard and abs(cluster_hard["price"]-entry) <= abs(pivot_hard["price"]-entry)+atr_value*.10 else min(hard, key=lambda item: abs(item["price"]-entry), default=None)
    first = nearest_hard if nearest_hard and abs(nearest_hard["price"]-entry)/risk >= params.short_plan_min_r else None
    if first is None:
        valid = [item for item in primary if abs(item["price"]-entry)/risk >= params.minimum_t1_r]
        if nearest_hard:
            hard_distance = abs(nearest_hard["price"]-entry)
            valid = [item for item in valid if abs(item["price"]-entry) <= hard_distance+atr_value*.05]
        first = min(valid, key=lambda item: (abs(item["price"]-entry), -item["priority"]), default=None)
    if first is None: return {"valid": False, "reason": "insufficient_room_before_first_obstacle", "entry": entry, "stop": stop, "risk_atr": risk_atr, "stop_source": stop_source, "target_count": 0}
    targets, used = [first], [first["price"]]
    first_r, short_plan = abs(first["price"]-entry)/risk, abs(first["price"]-entry)/risk < params.minimum_t1_r
    if not short_plan:
        for ordinal in (2, 3):
            pivot = _nearest_pivot(pivot_pool, price=entry, direction=direction, minimum_distance=abs(targets[-1]["price"]-entry)+min_distance, maximum_age_bars=params.sr_maximum_age_bars, current_index=current_index, exclude_prices=used, tolerance=atr_value*.10)
            fib = entry+direction*target_basis*float(ordinal)
            pivot_option = {"price": pivot[1], "source": f"new_confirmed_pivot_t{ordinal}", "priority": 16} if pivot and direction*(pivot[1]-targets[-1]["price"]) > min_distance else None
            fib_option = {"price": fib, "source": f"adaptive_{ordinal}r", "priority": 1} if direction*(fib-targets[-1]["price"]) > min_distance else None
            chosen = pivot_option or fib_option or {"price": targets[-1]["price"]+direction*target_basis, "source": f"adaptive_extension_t{ordinal}", "priority": 1}
            targets.append(chosen); used.append(chosen["price"])
    values = [item["price"] for item in targets]
    geometry = direction > 0 and stop < entry and all(value > entry for value in values) or direction < 0 and stop > entry and all(value < entry for value in values)
    if not geometry: return {"valid": False, "reason": "directional_geometry_invariant_failed", "entry": entry, "stop": stop, "targets": values, "target_count": 0}
    return {"valid": True, "direction": direction, "entry": entry, "stop": stop, "targets": values, "target_sources": [item["source"] for item in targets], "target_count": len(values), "short_plan": short_plan, "risk": risk, "risk_atr": risk_atr, "target_basis_risk": target_basis, "first_rr": first_r, "stop_source": stop_source, "method": "current_role_cluster_then_pivot_then_secondary", "post_target1_trail": {"enabled": True, "length": 22, "atr_multiple": 3.0, "never_loosen": True}}


def _serialize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    output = dict(plan)
    for key in ("entry", "stop", "risk", "target_basis_risk", "first_rr", "risk_atr"):
        if key in output and output[key] is not None: output[key] = _rounded(output[key])
    if "targets" in output: output["targets"] = [_rounded(value) for value in output.get("targets") or []]
    return output


def _serialize_numeric_mapping(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value: return None
    output = {}
    for key, item in value.items():
        if isinstance(item, dict): output[key] = _serialize_numeric_mapping(item)
        elif isinstance(item, (int, str, bool)) or item is None: output[key] = item
        else: output[key] = _rounded(item)
    return output


def _integrity(*, price: float, support: dict[str, Any] | None, resistance: dict[str, Any] | None, plan: dict[str, Any]) -> dict[str, Any]:
    issues = []
    if support and float(support["low"]) > price: issues.append("support_above_price")
    if resistance and float(resistance["high"]) < price: issues.append("resistance_below_price")
    if support and resistance and float(support["level"]) >= float(resistance["level"]): issues.append("support_resistance_order_invalid")
    if plan.get("valid"):
        direction, entry, stop = int(plan.get("direction") or 0), _finite(plan.get("entry")), _finite(plan.get("stop"))
        targets = [_finite(item) for item in plan.get("targets") or []]
        if direction > 0 and not (entry is not None and stop is not None and stop < entry and all(item is not None and item > entry for item in targets)): issues.append("long_plan_geometry_invalid")
        if direction < 0 and not (entry is not None and stop is not None and stop > entry and all(item is not None and item < entry for item in targets)): issues.append("short_plan_geometry_invalid")
    return {"ok": not issues, "issues": issues, "support_below_price": not support or float(support["low"]) <= price, "resistance_above_price": not resistance or float(resistance["high"]) >= price, "directional_plan_geometry": not any("plan_geometry" in item for item in issues)}


__all__ = [name for name in globals() if name.startswith("_")]
