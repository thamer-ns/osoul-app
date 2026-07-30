from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine_core.sc_feature_pack_v8 import (
    SC_FEATURE_VERSION,
    build_sc_feature_pack,
)


def _frame(rows: int = 260) -> pd.DataFrame:
    index = pd.date_range(
        "2025-01-01",
        periods=rows,
        freq="h",
        tz="UTC",
    )
    base = np.linspace(100.0, 118.0, rows)
    wave = np.sin(np.linspace(0.0, 18.0, rows)) * 1.8
    close = base + wave
    open_ = close - np.cos(np.linspace(0.0, 12.0, rows)) * 0.35
    high = np.maximum(open_, close) + 0.7
    low = np.minimum(open_, close) - 0.7
    volume = np.linspace(1_000_000, 1_400_000, rows)
    frame = pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )
    prior_high = float(frame["High"].iloc[-31:-1].max())
    frame.iloc[-1, frame.columns.get_loc("Open")] = prior_high - 0.15
    frame.iloc[-1, frame.columns.get_loc("Close")] = prior_high + 1.10
    frame.iloc[-1, frame.columns.get_loc("High")] = prior_high + 1.45
    frame.iloc[-1, frame.columns.get_loc("Low")] = prior_high - 0.40
    frame.iloc[-1, frame.columns.get_loc("Volume")] = 2_400_000
    return frame


def test_feature_pack_is_deterministic_and_serializable():
    frame = _frame()
    first = build_sc_feature_pack(frame, "1h")
    second = build_sc_feature_pack(frame.copy(deep=True), "60m")

    assert first == second
    assert first["ok"] is True
    assert first["version"] == SC_FEATURE_VERSION
    assert first["closed_candles_only"] is True
    assert first["interval"] == "1h"
    assert first["event_code"] != "NONE"
    assert set(first["evidence_axes"]) == {
        "structure",
        "trigger",
        "participation",
        "risk_geometry",
        "channel_range",
    }
    assert isinstance(first["reasons"], list)
    assert isinstance(first["warnings"], list)


def test_feature_pack_rejects_short_history_without_guessing():
    result = build_sc_feature_pack(_frame(40), "5m")

    assert result["ok"] is False
    assert result["reason"] == "insufficient_closed_candles"
    assert result["have"] == 40
    assert result["need"] >= 60


def test_zero_volume_does_not_create_false_volume_confirmation():
    frame = _frame()
    frame["Volume"] = 0.0

    result = build_sc_feature_pack(frame, "1d")

    assert result["ok"] is True
    assert result["volume"]["trusted"] is False
    assert result["volume"]["participation"] is False
    assert "volume_not_trusted_for_this_instrument" in result["warnings"]
