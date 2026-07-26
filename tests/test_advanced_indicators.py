import numpy as np
import pandas as pd

from technical_indicators.advanced_v2 import compute_advanced_technical_pack


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
