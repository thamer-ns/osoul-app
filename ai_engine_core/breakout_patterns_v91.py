"""SC-V91 post-validation for the Python breakout-pattern contract.

SC-V90 applies the asset-aware volume policy to most breakouts, but a bearish
break-and-role-reversal retest could remain confirmed when a trusted stock-volume
feed explicitly failed the required participation test. V91 keeps the pattern
visible as FORMING while preventing it from entering the confirmed signal path.
"""
from __future__ import annotations

import copy
from typing import Any

from . import breakout_patterns_v90 as _v90

ENGINE_VERSION = "SC-V91-PY-1.1"
_ORIGINAL_ANALYZE = _v90.analyze_breakout_patterns


def _rebuild(result: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(result)
    patterns = [
        item for item in output.get("patterns") or [] if isinstance(item, dict)
    ]
    confirmed = [item for item in patterns if item.get("status") == "CONFIRMED"]
    forming = [item for item in patterns if item.get("status") == "FORMING"]
    signed = sum(
        int(item.get("direction") or 0) * int(item.get("confidence") or 0)
        for item in confirmed
    )
    if not confirmed:
        signed = sum(
            int(item.get("direction") or 0)
            * int(item.get("confidence") or 0)
            * 0.25
            for item in forming[:2]
        )
    denominator = (
        sum(int(item.get("confidence") or 0) for item in confirmed)
        or sum(
            int(item.get("confidence") or 0) * 0.25
            for item in forming[:2]
        )
        or 1.0
    )
    score = max(-100.0, min(100.0, signed / denominator * 100.0))
    output["direction_score"] = round(score, 2)
    output["bias"] = (
        "bullish" if score >= 20 else "bearish" if score <= -20 else "neutral"
    )
    output["confidence"] = max(
        (int(item.get("confidence") or 0) for item in confirmed),
        default=max(
            (int(item.get("confidence") or 0) for item in forming),
            default=0,
        ),
    )

    confirmed_keys = {
        (
            str(item.get("name") or ""),
            "buy" if int(item.get("direction") or 0) > 0 else "sell",
        )
        for item in confirmed
    }
    signals: list[dict[str, Any]] = []
    for raw in output.get("signals") or []:
        if not isinstance(raw, dict):
            continue
        key = (str(raw.get("kind") or ""), str(raw.get("direction") or ""))
        if key not in confirmed_keys:
            continue
        signal = copy.deepcopy(raw)
        signal["type"] = "SC-V91"
        signals.append(signal)
    output["signals"] = signals
    output["evidence"] = [
        f"{item.get('name')}: {item.get('reason')} "
        f"({int(item.get('confidence') or 0)}/100)"
        for item in patterns[:8]
    ]
    features = {
        str(key): value
        for key, value in dict(output.get("features") or {}).items()
        if not str(key).startswith("pattern_")
    }
    features.update(
        {
            "breakout_pattern_count": len(patterns),
            "breakout_confirmed_count": len(confirmed),
            "breakout_forming_count": len(forming),
            "breakout_direction_score": round(score, 3),
            "breakout_bullish": int(
                any(int(item.get("direction") or 0) > 0 for item in confirmed)
            ),
            "breakout_bearish": int(
                any(int(item.get("direction") or 0) < 0 for item in confirmed)
            ),
        }
    )
    for item in patterns:
        features[
            f"pattern_{item.get('pattern_id')}_{str(item.get('status') or '').lower()}"
        ] = 1
    output["features"] = features
    output["summary"] = (
        f"{len(confirmed)} نموذج اختراق مؤكد و{len(forming)} نموذج تحت التكوين"
        if patterns
        else "لا يوجد نموذج اختراق واضح على آخر إغلاق"
    )
    primary = confirmed[0] if confirmed else forming[0] if forming else None
    output["risk_reference"] = (
        {
            "pattern": primary.get("name"),
            "direction": (
                "buy" if int(primary.get("direction") or 0) > 0 else "sell"
            ),
            "boundary": primary.get("boundary"),
            "stop_reference": primary.get("stop_reference"),
            "measured_target": primary.get("measured_target"),
            "height": primary.get("height"),
        }
        if primary
        else {}
    )
    output["version"] = ENGINE_VERSION
    return output


def analyze_breakout_patterns(
    frame: Any,
    *,
    symbol: str = "",
    timeframe: str = "1d",
) -> dict[str, Any]:
    result = _ORIGINAL_ANALYZE(frame, symbol=symbol, timeframe=timeframe)
    if not isinstance(result, dict) or not result.get("ok"):
        return result
    output = copy.deepcopy(result)
    policy = (
        output.get("volume_policy")
        if isinstance(output.get("volume_policy"), dict)
        else {}
    )
    if policy.get("mode") != "required":
        output["version"] = ENGINE_VERSION
        return output
    changed = False
    for item in output.get("patterns") or []:
        if not isinstance(item, dict):
            continue
        if (
            item.get("pattern_id") == "role_reversal"
            and item.get("status") == "CONFIRMED"
            and item.get("volume_confirmed") is False
        ):
            item["status"] = "FORMING"
            item["confidence"] = min(72, int(item.get("confidence") or 0))
            item["reason"] = (
                str(item.get("reason") or "")
                + "؛ مشاركة الحجم الموثوق لم تؤكد التحول بعد"
            )
            changed = True
    return _rebuild(output) if changed else {**output, "version": ENGINE_VERSION}


def install_breakout_patterns_v91() -> None:
    if getattr(_v90.analyze_breakout_patterns, "_osoli_v91", False):
        return
    analyze_breakout_patterns._osoli_v91 = True  # type: ignore[attr-defined]
    _v90.analyze_breakout_patterns = analyze_breakout_patterns


__all__ = [
    "ENGINE_VERSION",
    "analyze_breakout_patterns",
    "install_breakout_patterns_v91",
]
