from __future__ import annotations

import pandas as pd

from ai_engine_core.breakout_patterns_v90 import analyze_breakout_patterns


def _rectangle_breakout() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC")
    rows = []
    for position in range(100):
        if position < 75:
            close = 95.0 + position * 0.12
            rows.append(
                {
                    "Open": close - 0.2,
                    "High": close + 0.8,
                    "Low": close - 0.8,
                    "Close": close,
                    "Volume": 1000.0,
                }
            )
        elif position < 99:
            close = 104.0 + (position % 3) * 0.4
            rows.append(
                {
                    "Open": close - 0.2,
                    "High": 110.0,
                    "Low": 100.0,
                    "Close": close,
                    "Volume": 1000.0,
                }
            )
        else:
            rows.append(
                {
                    "Open": 109.0,
                    "High": 113.0,
                    "Low": 108.5,
                    "Close": 112.0,
                    "Volume": 2200.0,
                }
            )
    return pd.DataFrame(rows, index=index)


def test_rectangle_breakout_requires_and_uses_closed_candle():
    report = analyze_breakout_patterns(
        _rectangle_breakout(), symbol="1120.SR", timeframe="1d"
    )

    assert report["ok"] is True
    confirmed = [item for item in report["patterns"] if item["status"] == "CONFIRMED"]
    assert any(item["pattern_id"] == "rectangle" for item in confirmed)
    rectangle = next(item for item in confirmed if item["pattern_id"] == "rectangle")
    assert rectangle["direction"] == 1
    assert rectangle["stop_reference"] < rectangle["boundary"]
    assert rectangle["measured_target"] > 112.0
    assert report["closed_candles_only"] is True


def test_forex_volume_is_optional_not_fabricated_confirmation():
    frame = _rectangle_breakout()
    frame["Volume"] = 0.0

    report = analyze_breakout_patterns(
        frame, symbol="EURUSD=X", timeframe="1h"
    )

    assert report["ok"] is True
    assert report["volume_policy"]["mode"] == "optional"
    assert report["volume_policy"]["confirmed"] is None
