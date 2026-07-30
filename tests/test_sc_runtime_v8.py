from __future__ import annotations

import inspect
from types import SimpleNamespace

import persistent_market_cache_v8 as persistent
import sc_runtime_v8 as runtime


def test_provider_rank_preserves_configured_order_before_observations(monkeypatch):
    providers = SimpleNamespace(
        configured_provider_order=lambda: ["a", "b", "c"],
        provider_status=lambda: [
            {"provider": "a", "circuit_open": False, "failures": 0},
            {"provider": "b", "circuit_open": False, "failures": 0},
            {"provider": "c", "circuit_open": False, "failures": 0},
        ],
    )
    monkeypatch.setattr(runtime, "_PROVIDER_STATS", {})

    assert runtime._ranked_order(providers) == ["a", "b", "c"]


def test_provider_rank_moves_observed_fast_healthy_source_first(monkeypatch):
    providers = SimpleNamespace(
        configured_provider_order=lambda: ["slow", "fast"],
        provider_status=lambda: [
            {"provider": "slow", "circuit_open": False, "failures": 0},
            {"provider": "fast", "circuit_open": False, "failures": 0},
        ],
    )
    monkeypatch.setattr(
        runtime,
        "_PROVIDER_STATS",
        {
            "slow": {
                "ewma_ms": 1800.0,
                "successes": 4.0,
                "failures": 0.0,
            },
            "fast": {
                "ewma_ms": 120.0,
                "successes": 4.0,
                "failures": 0.0,
            },
        },
    )

    assert runtime._ranked_order(providers) == ["fast", "slow"]


def test_runtime_has_independent_pools_and_updates_router_imports():
    source = inspect.getsource(runtime)

    assert "history" in runtime._EXECUTORS
    assert "quotes" in runtime._EXECUTORS
    assert "financial" in runtime._EXECUTORS
    assert "active >= _POOL_SIZES[group]" in source
    assert "router.fetch_history = fetch_history" in source
    assert "router.fetch_quote = fetch_quote" in source
    assert "total_deadline_exceeded" in source
    assert "persistent_stale_while_revalidate" in inspect.getsource(persistent)
    assert runtime._HISTORY_DEADLINE < 6.0
    assert runtime._QUOTE_DEADLINE < 3.0
