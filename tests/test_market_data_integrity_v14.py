from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import analysis_routes_v5
import financial_providers_v5 as financial
import market_data_integrity_v14 as integrity
import market_providers_v5 as providers


class _Response:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _Session:
    def __init__(self, response: _Response | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _record(timestamp: int, local_text: str = "2026-07-30 10:00:00") -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "datetime": local_text,
        "open": "100",
        "high": "102",
        "low": "99",
        "close": "101",
        "volume": "500",
    }


def test_strict_request_executes_one_http_attempt(monkeypatch) -> None:
    session = _Session(error=TimeoutError("network timeout"))
    failures: list[tuple[str, str]] = []
    monkeypatch.setattr(providers, "_SESSION", session)
    monkeypatch.setattr(providers, "_circuit_allows", lambda _provider: True)
    monkeypatch.setattr(providers, "_circuit_failure", lambda provider, reason: failures.append((provider, reason)))

    payload, reason = integrity._strict_request_json(
        "fmp",
        "https://example.invalid/quote",
        params={"symbol": "2222.SR"},
        timeout=1.2,
    )

    assert payload is None
    assert reason in {"timeouterror", "request_timeout"}
    assert len(session.calls) == 1
    assert isinstance(session.calls[0]["timeout"], tuple)
    assert len(failures) == 1


def test_strict_request_does_not_retry_rate_limit(monkeypatch) -> None:
    session = _Session(_Response(429, {"message": "rate limit"}))
    monkeypatch.setattr(providers, "_SESSION", session)
    monkeypatch.setattr(providers, "_circuit_allows", lambda _provider: True)
    monkeypatch.setattr(providers, "_circuit_failure", lambda *_args: None)

    payload, reason = integrity._strict_request_json(
        "eodhd",
        "https://example.invalid/history",
        timeout=1.0,
    )

    assert payload is None
    assert reason == "rate_limit"
    assert len(session.calls) == 1


def test_frame_prefers_unambiguous_numeric_timestamp() -> None:
    expected = datetime(2026, 7, 30, 7, 0, tzinfo=timezone.utc)
    frame = integrity._frame_from_records_utc(
        [_record(int(expected.timestamp()))],
        timezone_hint="Asia/Riyadh",
    )

    assert len(frame) == 1
    assert frame.index.tz is not None
    assert frame.index[0].to_pydatetime() == expected
    assert float(frame.iloc[0]["Close"]) == 101.0


def test_naive_saudi_intraday_text_is_converted_to_utc() -> None:
    frame = integrity._frame_from_records_utc(
        [
            {
                "datetime": "2026-07-30 10:00:00",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            }
        ],
        timezone_hint="Asia/Riyadh",
    )

    assert frame.index[0].hour == 7
    assert str(frame.index.tz) == "UTC"


def test_operating_cash_flow_never_uses_investing_cash_flow(monkeypatch) -> None:
    original = tuple(financial._CANONICAL_ALIASES["operating_cash_flow"])
    monkeypatch.setitem(
        financial._CANONICAL_ALIASES,
        "operating_cash_flow",
        original,
    )

    integrity._install_financial_alias_integrity()

    aliases = financial._CANONICAL_ALIASES["operating_cash_flow"]
    assert "cashflowFromInvestment" not in aliases
    assert "netCashProvidedByOperatingActivities" in aliases
    row = {
        "cashflowFromInvestment": 999,
        "netCashProvidedByOperatingActivities": 123,
    }
    assert financial._first(row, aliases) == 123.0


def test_integrity_installs_after_v9_and_before_views() -> None:
    source = inspect.getsource(analysis_routes_v5.install_analysis_routes)
    runtime = source.index("install_sc_runtime_v9()")
    integrity_install = source.index("install_market_data_integrity_v14()")
    views_import = source.index("import views")
    assert runtime < integrity_install < views_import


def test_quote_refresh_is_per_symbol_single_flight() -> None:
    source = inspect.getsource(integrity._install_parallel_quote_refresh)
    assert 'runtime._submit_once("quotes", symbol' in source
    assert "deadline = time.monotonic() + runtime._QUOTE_BUDGET" in source
    assert "provider_batch([symbol])" in source
