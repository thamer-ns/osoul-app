from __future__ import annotations

import pandas as pd

from candle_confirmation import completed_candles, is_bar_closed


def _frame(index):
    values = range(1, len(index) + 1)
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": values,
            "Volume": [100] * len(index),
        },
        index=pd.DatetimeIndex(index),
    )


def test_daily_bar_waits_through_trade_at_last_phase():
    stamp = pd.Timestamp("2026-07-27 00:00", tz="Asia/Riyadh")
    assert not is_bar_closed(stamp, "1d", now="2026-07-27 15:19+03:00")
    assert is_bar_closed(stamp, "1d", now="2026-07-27 15:20+03:00")


def test_intraday_live_bar_is_excluded_but_previous_bar_is_kept():
    frame = _frame(
        [
            pd.Timestamp("2026-07-27 14:00", tz="Asia/Riyadh"),
            pd.Timestamp("2026-07-27 15:00", tz="Asia/Riyadh"),
        ]
    )
    closed = completed_candles(frame, "60m", now="2026-07-27 15:10+03:00")
    assert list(closed.index) == [frame.index[0]]
    assert closed.attrs["candle_confirmation"]["excluded_incomplete_bars"] == 1


def test_last_intraday_bar_closes_at_exchange_close_not_nominal_hour():
    stamp = pd.Timestamp("2026-07-27 15:00", tz="Asia/Riyadh")
    assert not is_bar_closed(stamp, "60m", now="2026-07-27 15:19+03:00")
    assert is_bar_closed(stamp, "60m", now="2026-07-27 15:20+03:00")


def test_current_week_and_month_are_conservatively_excluded():
    weekly = pd.Timestamp("2026-07-30 00:00", tz="Asia/Riyadh")
    monthly = pd.Timestamp("2026-07-31 00:00", tz="Asia/Riyadh")
    now = "2026-07-27 16:00+03:00"
    assert not is_bar_closed(weekly, "1wk", now=now)
    assert not is_bar_closed(monthly, "1mo", now=now)
