from __future__ import annotations

import inspect
from types import SimpleNamespace

import pandas as pd

import analysis_routes_v5 as routes
import bounded_twelvedata_v9 as bounded
import market_providers_v5 as providers
import persistent_market_cache_v8 as persistent
import sc_runtime_v8 as runtime
import sc_runtime_v9 as runtime_v9


def test_provider_rank_preserves_configured_order_before_observations(monkeypatch):
    providers_stub = SimpleNamespace(
        configured_provider_order=lambda: ["a", "b", "c"],
        provider_status=lambda: [
            {"provider": "a", "circuit_open": False, "failures": 0},
            {"provider": "b", "circuit_open": False, "failures": 0},
            {"provider": "c", "circuit_open": False, "failures": 0},
        ],
    )
    monkeypatch.setattr(runtime, "_PROVIDER_STATS", {})

    assert runtime._ranked_order(providers_stub) == ["a", "b", "c"]


def test_provider_rank_moves_observed_fast_healthy_source_first(monkeypatch):
    providers_stub = SimpleNamespace(
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

    assert runtime._ranked_order(providers_stub) == ["fast", "slow"]


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


def test_bounded_twelvedata_installs_before_v8_inside_v9_runtime():
    route_source = inspect.getsource(routes)
    runtime_source = inspect.getsource(runtime_v9.install_sc_runtime_v9)

    assert "install_sc_runtime_v9()" in route_source
    assert runtime_source.index("install_bounded_twelvedata_v9()") < runtime_source.index(
        "install_sc_runtime_v8()"
    )


def test_bounded_twelvedata_history_uses_one_direct_request(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "values": [
                    {
                        "datetime": "2026-07-29",
                        "open": "10",
                        "high": "11",
                        "low": "9",
                        "close": "10.5",
                        "volume": "1000",
                    }
                ]
            }

    class Session:
        def __init__(self):
            self.calls: list[tuple[str, dict, tuple[float, float]]] = []

        def get(self, url, *, params, timeout):
            self.calls.append((url, params, timeout))
            return Response()

    session = Session()
    monkeypatch.setattr(bounded, "_SESSION", session)
    monkeypatch.setattr(
        providers,
        "_secret",
        lambda name: "secret" if name == "TWELVEDATA_API_KEY" else "",
    )

    frame, resolved = bounded._history_adapter("2222.SR", "1d", 1)

    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 1
    assert resolved == "2222:XSAU"
    assert len(session.calls) == 1
    _url, params, timeout = session.calls[0]
    assert params["symbol"] == "2222"
    assert params["exchange"] == "XSAU"
    assert sum(timeout) <= bounded._HISTORY_BUDGET + 0.001


def test_bounded_twelvedata_failure_never_retries(monkeypatch):
    class Session:
        calls = 0

        def get(self, url, *, params, timeout):
            _ = url, params, timeout
            self.calls += 1
            raise TimeoutError("slow provider")

    session = Session()
    monkeypatch.setattr(bounded, "_SESSION", session)
    monkeypatch.setattr(
        providers,
        "_secret",
        lambda name: "secret" if name == "TWELVEDATA_API_KEY" else "",
    )

    frame, _resolved = bounded._history_adapter("AAPL", "1d", 1)

    assert frame.empty
    assert session.calls == 1
