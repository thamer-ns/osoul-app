"""Canonical timeframe contract shared by Osoli integrations.

Wire values are intentionally lowercase and unambiguous: ``m`` means minute,
``mo`` means month, and ``wk`` means week.  Consumers must normalize before
upper-casing or applying unit parsing.
"""
from __future__ import annotations

import re
from typing import Any

CANONICAL_TIMEFRAMES = (
    "1m", "2m", "3m", "5m", "10m", "15m", "30m", "45m",
    "1h", "2h", "3h", "4h", "6h", "8h", "12h",
    "1d", "1wk", "1mo", "2mo", "3mo",
)

_ALIAS_MAP = {
    "1": "1m", "2": "2m", "3": "3m", "5": "5m", "10": "10m",
    "15": "15m", "30": "30m", "45": "45m", "60": "1h",
    "120": "2h", "180": "3h", "240": "4h", "360": "6h",
    "480": "8h", "720": "12h",
    "d": "1d", "1d": "1d", "day": "1d", "daily": "1d",
    "w": "1wk", "1w": "1wk", "wk": "1wk", "1wk": "1wk",
    "week": "1wk", "weekly": "1wk",
    "m": "1mo", "mo": "1mo", "1mo": "1mo", "month": "1mo",
    "monthly": "1mo",
}


def canonical_timeframe(value: Any, *, strict: bool = True) -> str:
    raw = str(value or "").strip().lower().replace(" ", "")
    if not raw:
        raise ValueError("الفاصل مطلوب")
    normalized = _ALIAS_MAP.get(raw, raw)
    match = re.fullmatch(r"([1-9]\d*)(m|h|d|wk|mo)", normalized)
    if match is None:
        raise ValueError("صيغة الفاصل غير مدعومة")
    count = int(match.group(1))
    unit = match.group(2)
    normalized = f"{count}{unit}"
    if strict and normalized not in CANONICAL_TIMEFRAMES:
        raise ValueError("الفاصل خارج قائمة التكامل المدعومة")
    return normalized


def timeframe_minutes(value: Any) -> int:
    frame = canonical_timeframe(value, strict=False)
    match = re.fullmatch(r"(\d+)(m|h|d|wk|mo)", frame)
    if match is None:  # pragma: no cover - canonical_timeframe already guards
        raise ValueError("فاصل غير صالح")
    count = int(match.group(1))
    factors = {"m": 1, "h": 60, "d": 1_440, "wk": 10_080, "mo": 43_200}
    return count * factors[match.group(2)]


def bot_wire_timeframe(value: Any) -> str:
    """Return the exact wire value accepted by both Osoli and the market bot."""
    return canonical_timeframe(value)


__all__ = [
    "CANONICAL_TIMEFRAMES",
    "bot_wire_timeframe",
    "canonical_timeframe",
    "timeframe_minutes",
]
