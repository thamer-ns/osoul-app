"""Closed-candle selection for Saudi-market technical analysis.

Charts may display the live candle, but decisions, breakouts, stops, targets and
backtests must only consume bars whose close time can be proven.  The helper is
kept independent from Streamlit and providers so every analysis path uses the
same rule.
"""
from __future__ import annotations

import calendar
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

EXCHANGE_TIMEZONE = ZoneInfo("Asia/Riyadh")
# Saudi Exchange equities can still change through the closing auction and
# trade-at-last phases, so analysis waits until 15:20 local time.
SESSION_CLOSE = time(15, 20)

_INTERVAL_MINUTES = {
    "1m": 1,
    "2m": 2,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "45m": 45,
    "60m": 60,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "240m": 240,
}


def normalize_interval(interval: str) -> str:
    value = str(interval or "1d").strip().lower()
    aliases = {
        "d": "1d",
        "day": "1d",
        "daily": "1d",
        "1day": "1d",
        "w": "1wk",
        "1w": "1wk",
        "week": "1wk",
        "weekly": "1wk",
        "1week": "1wk",
        "m": "1mo",
        "mo": "1mo",
        "month": "1mo",
        "monthly": "1mo",
        "1month": "1mo",
        "60min": "60m",
        "4hr": "4h",
        "4hours": "4h",
    }
    return aliases.get(value, value)


def _exchange_timestamp(value: Any) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(stamp):
        return None
    try:
        if stamp.tzinfo is None:
            return stamp.tz_localize(EXCHANGE_TIMEZONE)
        return stamp.tz_convert(EXCHANGE_TIMEZONE)
    except Exception:
        return None


def _session_close_for_date(stamp: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(
        datetime.combine(stamp.date(), SESSION_CLOSE, tzinfo=EXCHANGE_TIMEZONE)
    )


def _last_saudi_weekday(year: int, month: int) -> int:
    day = calendar.monthrange(year, month)[1]
    # Python weekday: Friday=4, Saturday=5.
    while datetime(year, month, day).weekday() in {4, 5}:
        day -= 1
    return day


def bar_close_time(timestamp: Any, interval: str) -> pd.Timestamp | None:
    """Return the earliest time at which the supplied bar is final."""
    stamp = _exchange_timestamp(timestamp)
    if stamp is None:
        return None

    normalized = normalize_interval(interval)
    if normalized in _INTERVAL_MINUTES:
        session_close = _session_close_for_date(stamp)
        # Provider timestamps are treated as bar-open timestamps.  The final
        # intraday bar is complete at the exchange close even when its nominal
        # interval would extend past 15:20.
        nominal_close = stamp + pd.Timedelta(minutes=_INTERVAL_MINUTES[normalized])
        if stamp >= session_close:
            return stamp
        return min(nominal_close, session_close)

    if normalized == "1d":
        return _session_close_for_date(stamp)

    if normalized == "1wk":
        # Osoli resamples Saudi weeks with W-THU, so the label is Thursday.
        return _session_close_for_date(stamp)

    if normalized == "1mo":
        day = _last_saudi_weekday(stamp.year, stamp.month)
        return pd.Timestamp(
            datetime.combine(
                datetime(stamp.year, stamp.month, day).date(),
                SESSION_CLOSE,
                tzinfo=EXCHANGE_TIMEZONE,
            )
        )

    return None


def is_bar_closed(timestamp: Any, interval: str, now: Any | None = None) -> bool:
    close_time = bar_close_time(timestamp, interval)
    if close_time is None:
        return False
    current = _exchange_timestamp(now if now is not None else datetime.now(EXCHANGE_TIMEZONE))
    return bool(current is not None and current >= close_time)


def completed_candles(
    frame: pd.DataFrame,
    interval: str,
    *,
    now: Any | None = None,
) -> pd.DataFrame:
    """Return a copy containing only bars proven closed at ``now``.

    Unknown/non-datetime indexes are handled conservatively by excluding the
    newest row.  Source lineage is preserved and augmented with the number of
    excluded live bars.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame() if not isinstance(frame, pd.DataFrame) else frame.copy()

    attrs = dict(getattr(frame, "attrs", {}) or {})
    normalized = normalize_interval(interval)
    if isinstance(frame.index, pd.DatetimeIndex):
        mask = [is_bar_closed(value, normalized, now=now) for value in frame.index]
        output = frame.loc[mask].copy()
    else:
        output = frame.iloc[:-1].copy() if len(frame) > 1 else frame.iloc[0:0].copy()

    excluded = max(0, int(len(frame) - len(output)))
    output.attrs.update(attrs)
    confirmation = {
        "mode": "closed_only",
        "interval": normalized,
        "excluded_incomplete_bars": excluded,
        "last_closed_bar": str(output.index[-1]) if not output.empty else None,
    }
    output.attrs["candle_confirmation"] = confirmation
    lineage = dict(output.attrs.get("data_lineage") or {})
    lineage.update(confirmation)
    output.attrs["data_lineage"] = lineage
    return output
