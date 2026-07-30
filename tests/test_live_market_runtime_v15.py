from __future__ import annotations

import time

import live_market_runtime_v15 as live


def _attempt(source: str) -> dict[str, object]:
    return {"provider": source, "ok": True, "elapsed_ms": 10}


def test_saudi_symbol_normalization_is_strict() -> None:
    assert live._saudi_symbol("2222") == ("2222", "2222.SR")
    assert live._saudi_symbol("TADAWUL:2222") == ("2222", "2222.SR")
    assert live._saudi_symbol("^TASI.SR") == ("TASI", "^TASI.SR")
    assert live._saudi_symbol("AAPL") is None
    assert live._saudi_symbol("EURUSD") is None


def test_consensus_prefers_direct_source_when_prices_agree() -> None:
    now = int(time.time())
    observations = [
        {
            "source": "sahmk",
            "price": 100.00,
            "prev_close": 99.0,
            "timestamp": now,
            "delayed": False,
            "priority": 0,
        },
        {
            "source": "twelvedata",
            "price": 100.20,
            "prev_close": 99.0,
            "timestamp": now,
            "delayed": False,
            "priority": 1,
        },
        {
            "source": "yahoo",
            "price": 100.10,
            "prev_close": 99.0,
            "timestamp": now,
            "delayed": True,
            "priority": 3,
        },
    ]
    payload = live._choose_consensus(
        "2222.SR",
        observations,
        [_attempt("sahmk"), _attempt("twelvedata"), _attempt("yahoo")],
    )
    assert payload["source"] == "sahmk"
    assert payload["price"] == 100.0
    assert payload["price_confidence"] == "high"
    assert payload["price_conflict"] is False
    assert payload["source_count"] == 3
    assert payload["decision_use"] == "live_context_only_closed_candle_confirmation"
    assert payload["browser_sources_used_for_decision"] is False


def test_three_source_outlier_uses_median_nearest_observation() -> None:
    now = int(time.time())
    observations = [
        {"source": "sahmk", "price": 125.0, "timestamp": now, "delayed": False, "priority": 0},
        {"source": "twelvedata", "price": 100.1, "timestamp": now, "delayed": False, "priority": 1},
        {"source": "yahoo", "price": 100.0, "timestamp": now, "delayed": True, "priority": 3},
    ]
    payload = live._choose_consensus("2222.SR", observations, [])
    assert payload["source"] == "twelvedata"
    assert payload["price_conflict"] is True
    assert payload["price_confidence"] == "low"


def test_yahoo_only_is_explicitly_delayed_low_confidence() -> None:
    payload = live._choose_consensus(
        "2222.SR",
        [
            {
                "source": "yahoo",
                "price": 31.5,
                "prev_close": 31.0,
                "timestamp": int(time.time()),
                "delayed": True,
                "priority": 3,
            }
        ],
        [_attempt("yahoo")],
    )
    assert payload["is_delayed"] is True
    assert payload["price_confidence"] == "low"
    assert payload["change_available"] is True


def test_non_saudi_quote_delegates_without_live_scraping() -> None:
    called: list[str] = []

    def fallback(symbol: str):
        called.append(symbol)
        return {"price": 12.0, "source": "existing"}, []

    payload, attempts = live.fetch_live_quote("AAPL", fallback=fallback)
    assert payload["price"] == 12.0
    assert attempts == []
    assert called == ["AAPL"]


def test_runtime_status_never_claims_browser_pages_are_decision_sources(monkeypatch) -> None:
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    status = live.runtime_status()
    assert status["browser_sources_used_for_decision"] is False
    assert status["closed_candle_confirmation_unchanged"] is True
    assert status["runtime_version"] == "15.0"
