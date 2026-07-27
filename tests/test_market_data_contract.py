from __future__ import annotations

import pandas as pd

import market_data


def test_batch_data_does_not_invent_zero_change_when_previous_close_missing(monkeypatch):
    monkeypatch.setattr(market_data, "get_ticker_symbol", lambda value: "1120.SR")
    monkeypatch.setattr(
        market_data,
        "fetch_google_finance_snapshot",
        lambda symbol: {"price": 50.0, "source": "google_finance"},
    )
    monkeypatch.setattr(market_data, "fetch_tradingview_snapshot", lambda symbol: {})
    monkeypatch.setattr(market_data, "fetch_investing_snapshot", lambda symbol: {})
    monkeypatch.setattr(market_data, "fetch_argaam_snapshot", lambda symbol: {})

    # Disable Twelve Data for this deterministic fallback test.
    import twelvedata_provider

    monkeypatch.setattr(twelvedata_provider, "get_quote", lambda symbol: {})
    result = market_data.fetch_batch_data(["1120.SR"])
    payload = result["1120.SR"]
    assert payload["price"] == 50.0
    assert payload["prev_close"] == 0.0
    assert payload["change_pct"] is None
    assert payload["change_available"] is False
