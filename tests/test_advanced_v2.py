import numpy as np
import pandas as pd

from technical_indicators.advanced_v2 import _rsi, compute_advanced_technical_pack


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


def test_rsi_handles_monotonic_and_flat_series():
    rising = pd.Series(np.arange(1.0, 80.0))
    falling = pd.Series(np.arange(80.0, 1.0, -1.0))
    flat = pd.Series(np.repeat(50.0, 80))

    assert _rsi(rising).iloc[-1] == 100.0
    assert _rsi(falling).iloc[-1] == 0.0
    assert _rsi(flat).iloc[-1] == 50.0


def test_timeframe_history_periods_are_sufficient():
    from views.analysis.technical import period_for_interval

    assert period_for_interval("1d") == "5y"
    assert period_for_interval("1wk") == "15y"
    assert period_for_interval("1mo") == "max"
    assert period_for_interval("5m") == "60d"


def test_pack_is_strict_json_serialisable_and_contains_no_nan():
    import json

    pack = compute_advanced_technical_pack(
        _sample_frame(),
        symbol="1120.SR",
        timeframe="1m",
    )
    encoded = json.dumps(pack, ensure_ascii=False, allow_nan=False)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_rls_intraday_projection_remains_finite_on_strong_trend():
    frame = _sample_frame(rows=300)
    frame["Close"] = np.geomspace(10.0, 100.0, len(frame))
    frame["Open"] = frame["Close"] * 0.999
    frame["High"] = frame["Close"] * 1.005
    frame["Low"] = frame["Close"] * 0.995
    pack = compute_advanced_technical_pack(frame, timeframe="1m")
    features = pack["rls_forecast"]["features"]
    assert np.isfinite(features["projected_horizon_return"])
    assert -1.0 < features["projected_horizon_return"] < 1.0
