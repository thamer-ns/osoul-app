from __future__ import annotations

import threading
import time
from concurrent.futures import Future

import pandas as pd

import market_data
import performance_runtime_v7 as runtime
import sc_runtime_v9 as v9
from ai_engine_core import breakout_patterns_v91 as breakout


def test_interval_period_policy_treats_1m_as_minute_and_1mo_as_month():
    import analysis_context_v7 as context

    original = context._period
    try:
        v9._install_interval_period_policy()
        assert context._period("1M") == "7d"
        assert context._period("1m") == "7d"
        assert context._period("1mo") == "20y"
        assert context._period("1wk") == "15y"
    finally:
        context._period = original


def test_mixed_quote_batch_fetches_the_uncached_subset(monkeypatch):
    calls: list[list[str]] = []

    def provider(symbols):
        calls.append(list(symbols))
        return {
            symbol: {
                "price": 200.0,
                "prev_close": 198.0,
                "source": "test",
            }
            for symbol in symbols
        }

    def submit_once(namespace, key, loader, saver):
        _ = namespace, key
        future = Future()
        result = loader()
        saver(result)
        future.set_result(result)
        return future

    monkeypatch.setattr(market_data, "fetch_batch_data", provider)
    monkeypatch.setattr(runtime, "_submit_once", submit_once)
    monkeypatch.setattr(runtime, "_wait", lambda future, timeout: future.result())
    monkeypatch.setattr(
        runtime,
        "_store_quote",
        lambda symbol, payload: runtime._QUOTE_CACHE.__setitem__(
            runtime._normalized_symbol(symbol),
            (time.monotonic(), dict(payload)),
        ),
    )
    runtime._QUOTE_CACHE.clear()
    runtime._QUOTE_CACHE["AAPL"] = (
        time.monotonic(),
        {"price": 100.0, "prev_close": 99.0, "source": "cache"},
    )

    v9._install_corrected_quote_batch()
    result = market_data.fetch_batch_data(["AAPL", "MSFT"])

    assert calls == [["MSFT"]]
    assert result["AAPL"]["price"] == 100.0
    assert result["MSFT"]["price"] == 200.0


def test_persistent_history_write_never_blocks_request_thread(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    original_saver = runtime._history_saver

    def slow_save(*args, **kwargs):
        _ = args, kwargs
        started.set()
        release.wait(timeout=2)
        return True

    monkeypatch.setattr(v9.persistent_cache, "save_history", slow_save)
    runtime._HISTORY_CACHE.clear()
    frame = pd.DataFrame(
        {
            "Open": [1.0],
            "High": [2.0],
            "Low": [0.5],
            "Close": [1.5],
            "Volume": [100.0],
        },
        index=pd.to_datetime(["2026-01-01"], utc=True),
    )
    key = ("AAPL", "5y", "1d", 5)

    try:
        v9._install_nonblocking_persistence()
        before = time.perf_counter()
        runtime._history_saver(key, frame)
        elapsed = time.perf_counter() - before

        assert elapsed < 0.10
        assert key in runtime._HISTORY_CACHE
        assert started.wait(timeout=1)
    finally:
        release.set()
        runtime._history_saver = original_saver


def test_latest_history_cache_ignores_period_key_mismatch():
    runtime._HISTORY_CACHE.clear()
    older = pd.DataFrame({"Close": [90.0]})
    newest = pd.DataFrame({"Close": [100.0]})
    now = time.monotonic()
    runtime._HISTORY_CACHE[("AAPL", "2y", "1d", 2)] = (now - 2, older)
    runtime._HISTORY_CACHE[("AAPL", "5y", "1d", 5)] = (now - 1, newest)

    result = v9.peek_latest_cached_history("aapl", interval="1d")

    assert float(result["Close"].iloc[-1]) == 100.0


def test_role_reversal_with_required_weak_volume_stays_forming(monkeypatch):
    monkeypatch.setattr(
        breakout,
        "_ORIGINAL_ANALYZE",
        lambda *args, **kwargs: {
            "ok": True,
            "version": "SC-V90-PY-1.0",
            "patterns": [
                {
                    "pattern_id": "role_reversal",
                    "name": "كسر وتحول / إعادة اختبار",
                    "family": "structure",
                    "direction": -1,
                    "status": "CONFIRMED",
                    "confidence": 89,
                    "boundary": 100.0,
                    "opposite_boundary": 102.0,
                    "height": 3.0,
                    "stop_reference": 102.0,
                    "measured_target": 97.0,
                    "reason": "دعم مكسور أعيد اختباره",
                    "volume_confirmed": False,
                    "detected_at": "2026-01-01",
                }
            ],
            "signals": [
                {
                    "type": "SC-V90",
                    "kind": "كسر وتحول / إعادة اختبار",
                    "direction": "sell",
                    "price": 99.0,
                    "level": 100.0,
                }
            ],
            "features": {"breakout_confirmed_count": 1},
            "evidence": [],
            "volume_policy": {"mode": "required", "confirmed": False},
        },
    )

    result = breakout.analyze_breakout_patterns(
        pd.DataFrame(),
        symbol="AAPL",
    )

    assert result["version"] == breakout.ENGINE_VERSION
    assert result["patterns"][0]["status"] == "FORMING"
    assert result["features"]["breakout_confirmed_count"] == 0
    assert result["signals"] == []
