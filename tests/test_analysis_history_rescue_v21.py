from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import analysis_context_v7 as context
import analysis_history_rescue_v21 as rescue
import market_data


def _payload(rows: int = 120) -> dict:
    start = 1_700_000_000
    timestamps = [start + index * 86_400 for index in range(rows)]
    close = [30.0 + index * 0.01 for index in range(rows)]
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [value - 0.05 for value in close],
                                "high": [value + 0.10 for value in close],
                                "low": [value - 0.10 for value in close],
                                "close": close,
                                "volume": [1_000_000 + index for index in range(rows)],
                            }
                        ]
                    },
                }
            ],
        }
    }


def test_parse_yahoo_chart_builds_valid_ohlcv_frame() -> None:
    frame, reason = rescue._parse(_payload())

    assert reason == ""
    assert len(frame) == 120
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"


def test_fetch_rescue_is_bounded_and_sets_auditable_lineage(monkeypatch) -> None:
    calls: list[dict] = []

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return _payload()

    class Session:
        @staticmethod
        def get(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return Response()

    monkeypatch.setattr(rescue, "_session", lambda: Session())

    frame, diagnostic = rescue.fetch_yahoo_history_rescue(
        "2290.SR",
        period="5y",
        interval="1d",
    )

    assert diagnostic["ok"] is True
    assert diagnostic["source"] == "yahoo"
    assert len(calls) == 1
    assert calls[0]["params"]["range"] == "5y"
    assert calls[0]["params"]["interval"] == "1d"
    assert calls[0]["timeout"] == rescue._TIMEOUT
    lineage = frame.attrs["data_lineage"]
    assert lineage["source"] == "yahoo"
    assert lineage["adapter"] == "chart_api_v21"
    assert lineage["cold_start_rescue"] is True


def test_invalid_symbol_never_starts_network_request(monkeypatch) -> None:
    monkeypatch.setattr(
        rescue,
        "_session",
        lambda: (_ for _ in ()).throw(AssertionError("network must not run")),
    )

    frame, diagnostic = rescue.fetch_yahoo_history_rescue(
        "https://example.com",
        period="5y",
        interval="1d",
    )

    assert frame.empty
    assert diagnostic["reason"] == "invalid_symbol"


def test_analysis_context_uses_rescue_when_routed_history_is_empty(
    monkeypatch,
) -> None:
    timestamps = pd.date_range("2025-01-01", periods=120, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "Open": [30.0] * 120,
            "High": [30.5] * 120,
            "Low": [29.5] * 120,
            "Close": [30.2] * 120,
            "Volume": [1_000_000.0] * 120,
        },
        index=timestamps,
    )
    frame.attrs["data_lineage"] = {
        "source": "yahoo",
        "cold_start_rescue": True,
    }

    monkeypatch.setattr(context, "install_analysis_context", lambda: None)
    monkeypatch.setattr(market_data, "get_chart_history", lambda *_args, **_kwargs: pd.DataFrame())
    monkeypatch.setattr(context, "_compatible_cached_history", lambda *_args: pd.DataFrame())
    monkeypatch.setattr(context, "_rescue_history", lambda *_args: frame.copy())
    monkeypatch.setattr(context, "completed_candles", lambda value, **_kwargs: value)
    monkeypatch.setattr(context, "_ORIGINAL_INDICATORS", lambda _frame: {"ok": True})
    monkeypatch.setattr(context, "_tenant_key", lambda: (0, 0))
    monkeypatch.setattr(context, "_CONTEXT_CACHE", {})

    result = context.build_analysis_context("2290.SR", "1D", refresh=True)

    assert len(result.history) == 120
    assert len(result.closed_history) == 120
    assert result.indicators == {"ok": True}
    assert result.fingerprint != "empty"


def test_no_history_returns_specific_retryable_diagnostic(monkeypatch) -> None:
    empty_context = context.AnalysisContext(
        symbol="2290.SR",
        timeframe="1D",
        interval="1d",
        period="5y",
        history=pd.DataFrame(),
        closed_history=pd.DataFrame(),
        indicators={},
        fingerprint="empty",
        timings={},
    )
    monkeypatch.setattr(context, "build_analysis_context", lambda *_args, **_kwargs: empty_context)
    monkeypatch.setattr(
        context,
        "performance_trace",
        lambda *_args: {"history_rescue_ok": 0.0},
    )

    report, returned = context.generate_with_context(
        lambda *_args, **_kwargs: {},
        "2290.SR",
        "1D",
    )

    assert returned is empty_context
    assert report["error"] == "no_data_within_budget"
    assert report["diagnostic_code"] == "analysis_history_unavailable"
    assert report["retryable"] is True
