import numpy as np
import pandas as pd

from technical_indicators.advanced_v2 import (
    compute_advanced_technical_pack,
    is_live_bar,
)


def _sample_frame(rows=320):
    index = pd.date_range("2024-01-01", periods=rows, freq="D")
    trend = np.linspace(20, 40, rows)
    noise = np.sin(np.arange(rows) / 8) * 0.4
    close = trend + noise
    return pd.DataFrame(
        {
            "Open": close - 0.1,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": np.linspace(100_000, 250_000, rows),
        },
        index=index,
    )


def test_advanced_pack_has_stable_contract():
    pack = compute_advanced_technical_pack(_sample_frame(), symbol="1120.SR", timeframe="1d")
    assert pack["bias"] in {"bullish", "bearish", "neutral"}
    assert -100 <= pack["direction_score"] <= 100
    assert 0 <= pack["confidence"] <= 100
    assert pack["meta"]["confirmation_rule"] == "closed_candle"
    for key in (
        "rls_forecast",
        "chaos_wrsi",
        "volume_profile_clusters",
        "trendline_breakout",
    ):
        result = pack[key]
        assert "bias" in result
        assert "direction_score" in result
        assert "confidence" in result
        assert "summary" in result


def test_confidence_is_separate_from_direction():
    pack = compute_advanced_technical_pack(_sample_frame(), timeframe="1d")
    assert pack["confidence"] >= 0
    assert pack["direction_score"] != pack["confidence"]


def test_saudi_weekly_bar_calendar():
    sunday = pd.Timestamp("2026-07-26 16:00", tz="Asia/Riyadh")
    assert not is_live_bar(pd.Timestamp("2026-07-23"), "1wk", sunday)
    assert is_live_bar(pd.Timestamp("2026-07-30"), "1wk", sunday)


def test_monthly_bar_is_live_before_final_trading_close():
    current = pd.Timestamp("2026-07-26 16:00", tz="Asia/Riyadh")
    assert is_live_bar(pd.Timestamp("2026-07-31"), "1mo", current)
