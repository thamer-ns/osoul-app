from __future__ import annotations

import pandas as pd

import market_providers_v5 as providers


def _valid_frame(rows: int = 40) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="D", tz="UTC")
    close = pd.Series([100.0 + index * 0.1 for index in range(rows)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": 1_000.0,
        },
        index=index,
    )


def test_record_normalization_produces_canonical_ohlcv():
    frame = providers._frame_from_records(
        [
            {
                "date": "2026-01-01",
                "open": "10",
                "high": "12",
                "low": "9",
                "close": "11",
                "volume": "1000",
            },
            {
                "date": "2026-01-02",
                "open": "11",
                "high": "13",
                "low": "10",
                "close": "12",
                "volume": "1200",
            },
        ]
    )

    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert float(frame.iloc[-1]["Close"]) == 12.0


def test_ohlcv_quality_rejects_invalid_candle_geometry():
    frame = _valid_frame()
    frame.loc[frame.index[-1], "High"] = 50.0
    result = providers.validate_ohlcv(frame, minimum_rows=20)
    assert result["ok"] is False
    assert any(str(issue).startswith("invalid_geometry") for issue in result["issues"])


def test_history_fusion_uses_first_provider_that_passes_quality(monkeypatch):
    calls = []

    monkeypatch.setattr(providers, "configured_provider_order", lambda: ["twelvedata", "fmp"])
    monkeypatch.setattr(providers, "_secret", lambda name: "configured")

    def empty(symbol, interval, years):
        calls.append("twelvedata")
        return pd.DataFrame(), symbol

    def good(symbol, interval, years):
        calls.append("fmp")
        return _valid_frame(), "1120.TADAWUL"

    monkeypatch.setitem(providers._HISTORY_ADAPTERS, "twelvedata", empty)
    monkeypatch.setitem(providers._HISTORY_ADAPTERS, "fmp", good)

    frame, attempts = providers.fetch_history(
        "1120.SR", interval="1d", years=2, minimum_rows=20
    )

    assert calls == ["twelvedata", "fmp"]
    assert not frame.empty
    assert frame.attrs["data_lineage"]["source"] == "fmp"
    assert [item["ok"] for item in attempts] == [False, True]
