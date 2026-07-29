from __future__ import annotations

import inspect

import pandas as pd

import market_data_router_v5 as router
import performance_runtime_v7 as runtime


def _frame(rows: int = 20) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": range(1, rows + 1),
            "High": range(2, rows + 2),
            "Low": [max(0.5, value - 0.5) for value in range(1, rows + 1)],
            "Close": [value + 0.25 for value in range(1, rows + 1)],
            "Volume": [1000] * rows,
        },
        index=index,
    )


def test_period_has_priority_over_legacy_default_years():
    assert router._years_from_request("7d", 5, "1m") == 1
    assert router._years_from_request("60d", 5, "15m") == 1
    assert router._years_from_request("2y", 5, "1d") == 2
    assert router._years_from_request("max", 5, "1mo") == 20
    assert router._years_from_request(None, 5, "1d") == 5


def test_analysis_windows_are_bounded_by_timeframe():
    assert runtime.analysis_row_limit("5m") == 1200
    assert runtime.analysis_row_limit("4h") == 1600
    assert runtime.analysis_row_limit("1d") == 1800
    assert runtime.analysis_row_limit("1wk") == 1200
    assert runtime.analysis_row_limit("1mo") == 600


def test_history_wrapper_reuses_process_cache():
    runtime._HISTORY_CACHE.clear()
    runtime._INFLIGHT.clear()
    calls = {"count": 0}

    def loader(symbol, period=None, interval="1d", years=5):
        calls["count"] += 1
        return _frame()

    wrapped = runtime._history_wrapper(loader)
    first = wrapped("1120.SR", period="2y", interval="1d", years=2)
    second = wrapped("1120.SR", period="2y", interval="1d", years=2)

    assert not first.empty
    assert not second.empty
    assert calls["count"] == 1
    assert second.attrs["data_lineage"]["cache_mode"] == "fresh"


def test_runtime_has_bounded_waits_and_stale_revalidation():
    source = inspect.getsource(runtime)
    assert "ThreadPoolExecutor" in source
    assert "OSOUL_HISTORY_INTERACTIVE_BUDGET_SECONDS" in source
    assert "OSOUL_QUOTE_INTERACTIVE_BUDGET_SECONDS" in source
    assert "OSOUL_PROVIDER_REQUEST_TIMEOUT_SECONDS" in source
    assert "stale_while_revalidate" in source
    assert "providers._MAX_RETRIES = 1" in source
    assert '_HISTORY_ADAPTERS["twelvedata"]' in source
