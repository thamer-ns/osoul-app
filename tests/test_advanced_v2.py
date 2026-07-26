import numpy as np
import pandas as pd

from technical_indicators.advanced_v2 import compute_advanced_technical_pack


def _sample_frame(rows=280):
    rng = np.random.default_rng(42)
    close = 100 + np.linspace(0, 30, rows) + rng.normal(0, 0.5, rows)
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 0.8,
            "Low": close - 0.8,
            "Close": close,
            "Volume": rng.integers(100_000, 500_000, rows),
        },
        index=pd.date_range("2025-01-01", periods=rows, freq="D"),
    )


def test_pack_has_stable_direction_and_confidence_schema():
    pack = compute_advanced_technical_pack(_sample_frame(), symbol="1120.SR", timeframe="1d")
    assert pack["bias"] in {"bullish", "bearish", "neutral"}
    assert -100 <= pack["direction_score"] <= 100
    assert 0 <= pack["confidence"] <= 100
    assert pack["meta"]["confirmation"] == "close"
    for key in ("rls_forecast", "chaos_wrsi", "volume_profile_clusters", "trendline_breakout"):
        result = pack[key]
        assert result["bias"] in {"bullish", "bearish", "neutral"}
        assert "summary" in result
        assert "direction_score" in result
        assert "confidence" in result
