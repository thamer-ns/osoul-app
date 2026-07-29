from __future__ import annotations

import inspect

import pandas as pd

import analysis_context_v7 as context
import performance_runtime_v7 as runtime


def _frame(rows: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0] * rows,
            "High": [102.0] * rows,
            "Low": [98.0] * rows,
            "Close": [101.0] * rows,
            "Volume": [1000.0] * rows,
        },
        index=index,
    )


def test_context_trims_large_histories_before_heavy_indicators():
    intraday = context._trim(_frame(5000), "5m")
    daily = context._trim(_frame(5000), "1d")
    monthly = context._trim(_frame(5000), "1mo")

    assert len(intraday) == 1200
    assert len(daily) == 1800
    assert len(monthly) == 600
    assert intraday.attrs["analysis_window"]["input_rows"] == 5000


def test_active_context_short_circuits_a_second_history_loader():
    frame = _frame(200)
    item = context.AnalysisContext(
        symbol="1120.SR",
        timeframe="1H",
        interval="1h",
        period="2y",
        history=frame,
        closed_history=frame,
        indicators={},
        fingerprint=context._fingerprint(frame),
    )
    calls = {"count": 0}

    def loader(*args, **kwargs):
        calls["count"] += 1
        return pd.DataFrame()

    wrapped = runtime._history_wrapper(loader)
    with context.active_context(item):
        result = wrapped("1120.SR", period="2y", interval="1h", years=2)

    assert len(result) == len(frame)
    assert calls["count"] == 0


def test_report_contract_exposes_required_phase_timings():
    source = inspect.getsource(context)
    for name in (
        "history_fetch_ms",
        "basic_indicators_ms",
        "fundamental_ms",
        "total_analysis_ms",
    ):
        assert name in source
    assert '"history_reused": True' in source
    assert '"indicators_reused": True' in source
