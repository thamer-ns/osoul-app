from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import live_market_runtime_v15 as live


def _attempt(source: str) -> dict[str, object]:
    return {"provider": source, "ok": True, "elapsed_ms": 10}


def _row(
    source: str,
    price: float,
    *,
    priority: int,
    delayed: bool | None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "source": source,
        "price": price,
        "prev_close": price - 1,
        "timestamp": int(time.time()),
        "priority": priority,
    }
    if delayed is not None:
        row["delayed"] = delayed
        row["delay_status"] = "delayed" if delayed else "realtime"
    else:
        row["delay_status"] = "unknown"
    return row


def _reset_state() -> None:
    with live._STATE_LOCK:
        live._CACHE.clear()
        live._INFLIGHT.clear()


def test_saudi_symbol_normalization_is_strict() -> None:
    assert live._saudi_symbol("2222") == ("2222", "2222.SR")
    assert live._saudi_symbol("TADAWUL:2222") == ("2222", "2222.SR")
    assert live._saudi_symbol("^TASI.SR") == ("TASI", "^TASI.SR")
    assert live._saudi_symbol("AAPL") is None
    assert live._saudi_symbol("EURUSD") is None


def test_consensus_prefers_direct_source_when_prices_agree() -> None:
    observations = [
        _row("sahmk", 100.00, priority=0, delayed=False),
        _row("twelvedata", 100.20, priority=1, delayed=None),
        _row("yahoo", 100.10, priority=3, delayed=True),
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
    observations = [
        _row("sahmk", 125.0, priority=0, delayed=False),
        _row("twelvedata", 100.1, priority=1, delayed=None),
        _row("yahoo", 100.0, priority=3, delayed=True),
    ]
    payload = live._choose_consensus("2222.SR", observations, [])
    assert payload["source"] == "twelvedata"
    assert payload["price_conflict"] is True
    assert payload["price_confidence"] == "low"


def test_yahoo_only_is_explicitly_delayed_low_confidence() -> None:
    payload = live._choose_consensus(
        "2222.SR",
        [_row("yahoo", 31.5, priority=3, delayed=True)],
        [_attempt("yahoo")],
    )
    assert payload["is_delayed"] is True
    assert payload["delay_status"] == "delayed"
    assert payload["price_confidence"] == "low"
    assert payload["change_available"] is True


def test_unknown_provider_delay_is_not_claimed_realtime() -> None:
    payload = live._choose_consensus(
        "2222.SR",
        [
            _row("twelvedata", 30.0, priority=1, delayed=None),
            _row("yahoo", 30.05, priority=3, delayed=True),
        ],
        [],
    )
    assert payload["delay_status"] == "unknown"
    assert payload["is_delayed"] is False
    assert payload["price_confidence"] == "medium"


def test_exchange_local_timestamp_is_normalized_to_utc() -> None:
    parsed = live._epoch(
        "2026-07-30 10:00:00",
        timezone_hint="Asia/Riyadh",
    )
    expected = int(
        datetime(2026, 7, 30, 7, 0, tzinfo=timezone.utc).timestamp()
    )
    assert parsed == expected


def test_non_saudi_quote_delegates_without_live_scraping() -> None:
    called: list[str] = []

    def fallback(symbol: str):
        called.append(symbol)
        return {"price": 12.0, "source": "existing"}, []

    payload, attempts = live.fetch_live_quote("AAPL", fallback=fallback)
    assert payload["price"] == 12.0
    assert attempts == []
    assert called == ["AAPL"]


def test_aliases_share_one_canonical_cache_entry(monkeypatch) -> None:
    _reset_state()
    calls: list[str] = []

    def load(symbol: str):
        calls.append(symbol)
        return live._choose_consensus(
            symbol,
            [_row("sahmk", 30.0, priority=0, delayed=False)],
            [],
        )

    monkeypatch.setattr(live, "_load_saudi_quote", load)
    first, _ = live.fetch_live_quote("2222")
    second, _ = live.fetch_live_quote("TADAWUL:2222")
    assert first["price"] == second["price"] == 30.0
    assert calls == ["2222.SR"]
    assert list(live._CACHE) == ["2222.SR"]


def test_separate_pools_do_not_starve_concurrent_symbols(monkeypatch) -> None:
    _reset_state()

    def provider(code: str, _symbol: str):
        time.sleep(0.02)
        return (
            _row("sahmk", float(code) / 100, priority=0, delayed=False),
            _attempt("sahmk"),
        )

    def unavailable(_code: str, _symbol: str):
        return {}, {"provider": "fallback", "ok": False, "reason": "test"}

    monkeypatch.setattr(live, "_quote_sahmk", provider)
    monkeypatch.setattr(live, "_quote_twelvedata", unavailable)
    monkeypatch.setattr(live, "_quote_yahoo", unavailable)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda symbol: live.fetch_live_quote(symbol)[0],
                ("1111", "2222", "3333", "4444"),
            )
        )
    elapsed = time.perf_counter() - started
    assert all(result.get("price") for result in results)
    assert elapsed < 1.0


def test_expired_stale_cache_is_not_returned(monkeypatch) -> None:
    _reset_state()
    with live._STATE_LOCK:
        live._CACHE["2222.SR"] = (
            time.monotonic() - 10,
            {"price": 30.0, "source": "sahmk"},
        )
    monkeypatch.setattr(live, "_MAX_STALE_CACHE_AGE", 1.0)
    monkeypatch.setattr(live, "_MAX_INFLIGHT_SYMBOLS", 0)
    called: list[str] = []

    def fallback(symbol: str):
        called.append(symbol)
        return {"price": 29.0, "source": "existing"}, []

    payload, _ = live.fetch_live_quote("2222", fallback=fallback)
    assert payload["source"] == "existing"
    assert called == ["2222.SR"]


def test_runtime_status_never_claims_browser_pages_are_decision_sources(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    status = live.runtime_status()
    assert status["browser_sources_used_for_decision"] is False
    assert status["closed_candle_confirmation_unchanged"] is True
    assert status["runtime_version"] == "16.0"
    assert status["separate_coordinator_and_source_pools"] is True
    assert status["canonical_symbol_single_flight"] is True
    assert status["delay_status_is_tristate"] is True
