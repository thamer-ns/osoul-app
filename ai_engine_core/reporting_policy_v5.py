"""Timeframe routing fixes shared by every v5 report consumer."""
from __future__ import annotations

_INSTALLED = False


def timeframe_to_interval(timeframe: str) -> str:
    raw = str(timeframe or "1d").strip()
    lower = raw.lower()
    # Preserve the crucial distinction: 1m is one minute, 1mo is one month.
    aliases = {
        "1m": "1m",
        "1min": "1m",
        "min1": "1m",
        "5m": "5m",
        "5min": "5m",
        "15m": "15m",
        "15min": "15m",
        "30m": "30m",
        "30min": "30m",
        "60m": "60m",
        "1h": "60m",
        "h": "60m",
        "4h": "4h",
        "240m": "4h",
        "1d": "1d",
        "d": "1d",
        "day": "1d",
        "1w": "1wk",
        "1wk": "1wk",
        "w": "1wk",
        "week": "1wk",
        "1mo": "1mo",
        "mo": "1mo",
        "month": "1mo",
        "monthly": "1mo",
    }
    return aliases.get(lower, "1d")


def install_reporting_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import reporting

    reporting._timeframe_to_interval = timeframe_to_interval
    reporting._reporting_policy_v5_installed = True
    _INSTALLED = True


__all__ = ["install_reporting_policy", "timeframe_to_interval"]
