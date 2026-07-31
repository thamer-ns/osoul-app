from __future__ import annotations

import inspect

import analysis_routes_v5 as routes
import bot_contract_runtime_v10 as contract_runtime
import persistent_cache_resilience_v10 as cache_resilience
from ai_engine_core import bot_bridge_v5 as bridge
from ai_engine_core.bot_remote_analysis_v8 import request_bot_analysis


def test_optional_persistent_cache_failure_never_blocks_runtime(monkeypatch):
    def fail_install() -> None:
        raise PermissionError("read-only optional cache")

    monkeypatch.setattr(cache_resilience, "_ORIGINAL_INSTALL", fail_install)
    monkeypatch.setattr(cache_resilience, "_AVAILABLE", None)
    monkeypatch.setattr(cache_resilience, "_LAST_ERROR", "")
    monkeypatch.setattr(cache_resilience, "_NEXT_RETRY", 0.0)

    assert cache_resilience._guarded_install() is False
    status = cache_resilience.runtime_status()
    assert status["available"] is False
    assert status["last_error"] == "PermissionError"
    assert status["fail_open"] is True


def test_unavailable_cache_short_circuits_all_database_operations(monkeypatch):
    calls: list[str] = []

    def fail_install() -> None:
        raise PermissionError("optional cache unavailable")

    def touched(*args, **kwargs):
        _ = args, kwargs
        calls.append("called")
        raise AssertionError("persistent operation must be short-circuited")

    monkeypatch.setattr(cache_resilience, "_ORIGINAL_INSTALL", fail_install)
    monkeypatch.setattr(cache_resilience, "_ORIGINAL_SAVE_HISTORY", touched)
    monkeypatch.setattr(cache_resilience, "_ORIGINAL_LOAD_HISTORY", touched)
    monkeypatch.setattr(cache_resilience, "_ORIGINAL_SAVE_QUOTE", touched)
    monkeypatch.setattr(cache_resilience, "_ORIGINAL_LOAD_QUOTE", touched)
    monkeypatch.setattr(cache_resilience, "_ORIGINAL_PRUNE", touched)
    monkeypatch.setattr(cache_resilience, "_AVAILABLE", None)
    monkeypatch.setattr(cache_resilience, "_LAST_ERROR", "")
    monkeypatch.setattr(cache_resilience, "_NEXT_RETRY", 0.0)

    assert cache_resilience._safe_save_history() is False
    assert cache_resilience._safe_load_history() is None
    assert cache_resilience._safe_save_quote() is False
    assert cache_resilience._safe_load_quote() is None
    cache_resilience._safe_prune()

    assert calls == []
    status = cache_resilience.runtime_status()
    assert status["short_circuit_unavailable_operations"] is True


def test_cache_resilience_installs_before_v9_runtime_and_contract_after():
    source = inspect.getsource(routes)

    assert source.index("install_persistent_cache_resilience_v10()") < source.index(
        "from sc_runtime_v9 import install_sc_runtime_v9"
    )
    assert source.index("install_sc_runtime_v9()") < source.index(
        "install_bot_contract_runtime_v10()"
    )


class _Response:
    def __init__(self, body: dict, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def json(self) -> dict:
        return self._body


class _RuntimeRequests:
    def __init__(self, body: dict) -> None:
        self.body = body
        self.calls: list[tuple[str, dict, tuple[float, float]]] = []

    def get(self, url, *, headers, timeout):
        self.calls.append((url, headers, timeout))
        return _Response(self.body)


class _AnalysisRequests:
    def __init__(self, body: dict, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code
        self.calls: list[tuple[str, dict, dict, tuple[float, float]]] = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append((url, headers, json, timeout))
        return _Response(self.body, self.status_code)


def _patch_bridge(monkeypatch, requests_object: object) -> None:
    monkeypatch.setattr(bridge, "_base_url", lambda: "https://bot.example")
    monkeypatch.setattr(
        bridge,
        "_sync_headers",
        lambda: {
            "X-Osoli-Sync-Token": "x" * 40,
            "X-Osoli-Sync-Channel": "a" * 64,
        },
    )
    monkeypatch.setattr(bridge, "requests", requests_object)


def _live_runtime_values() -> dict:
    return {
        "runtime_version": "61.0",
        "stale_fallback_age_bounded": True,
        "delay_status_is_tristate": True,
        "closed_candle_confirmation_unchanged": True,
        "closed_price_preserved": True,
        "live_price_persisted_as_analysis_price": False,
        "source_spread_label_correct": True,
    }


def _runtime_values(*, installed: bool = True) -> dict:
    return {
        "installed": installed,
        "feature_version": contract_runtime.EXPECTED_FEATURE_VERSION,
        "runtime_version": contract_runtime.EXPECTED_RUNTIME_VERSION,
        "indicator_contract": contract_runtime.EXPECTED_INDICATOR_CONTRACT,
        "failure_single_flight": True,
        "stale_fallback_age_bounded": True,
        "live_quote_overlay": True,
        "live_quote_changes_signal": False,
        "closed_candle_confirmation_unchanged": True,
        "closed_price_preserved": True,
        "live_quote_context": _live_runtime_values(),
    }


def _runtime_body(*, installed: bool = True, contract: str | None = None) -> dict:
    return {
        "ok": True,
        "contract": contract or contract_runtime.EXPECTED_CONTRACT,
        "mode": "opaque-channel-exact-plan-pull-sync",
        "remote_analysis": True,
        "same_plan_reuses_event_id": True,
        "tenant_ids_received": False,
        "token_in_url": False,
        "supported_frames": ["1m", "5m", "1d", "1w", "1mo"],
        "app_version": "4.4.1",
        "analysis_deadline_seconds": 8.0,
        "runtime": _runtime_values(installed=installed),
    }


def test_runtime_probe_requires_live_v61_engine(monkeypatch):
    requests_object = _RuntimeRequests(_runtime_body())
    _patch_bridge(monkeypatch, requests_object)

    result = contract_runtime._probe_runtime()

    assert result["ok"] is True
    assert result["contract"] == contract_runtime.EXPECTED_CONTRACT
    assert result["remote_analysis"] is True
    assert result["runtime_installed"] is True
    assert result["runtime_version"] == contract_runtime.EXPECTED_RUNTIME_VERSION
    assert result["feature_version"] == contract_runtime.EXPECTED_FEATURE_VERSION
    assert result["indicator_contract"] == contract_runtime.EXPECTED_INDICATOR_CONTRACT
    assert result["failure_single_flight"] is True
    assert result["stale_fallback_age_bounded"] is True
    assert result["closed_price_preserved"] is True
    assert all(result["capability_checks"].values())
    assert result["endpoint"] == "/integrations/osoli/runtime"
    assert len(requests_object.calls) == 1


def test_runtime_probe_rejects_uninstalled_wrong_or_unsafe_runtime(monkeypatch):
    requests_object = _RuntimeRequests(_runtime_body(installed=False))
    _patch_bridge(monkeypatch, requests_object)
    assert contract_runtime._probe_runtime()["reason"] == "runtime_not_installed"

    requests_object.body = _runtime_body(contract="old-contract")
    assert contract_runtime._probe_runtime()["reason"] == "contract_mismatch"

    wrong_runtime = _runtime_body()
    wrong_runtime["runtime"]["runtime_version"] = "58.0"
    requests_object.body = wrong_runtime
    assert contract_runtime._probe_runtime()["reason"] == "runtime_version_mismatch"

    unsafe_stale = _runtime_body()
    unsafe_stale["runtime"]["live_quote_context"][
        "stale_fallback_age_bounded"
    ] = False
    requests_object.body = unsafe_stale
    assert contract_runtime._probe_runtime()["reason"] == "live_quote_stale_unbounded"

    unsafe_delay = _runtime_body()
    unsafe_delay["runtime"]["live_quote_context"][
        "delay_status_is_tristate"
    ] = False
    requests_object.body = unsafe_delay
    assert (
        contract_runtime._probe_runtime()["reason"]
        == "live_quote_delay_unknown_unsafe"
    )

    unsafe_price = _runtime_body()
    unsafe_price["runtime"]["live_quote_context"][
        "live_price_persisted_as_analysis_price"
    ] = True
    requests_object.body = unsafe_price
    assert (
        contract_runtime._probe_runtime()["reason"]
        == "closed_price_may_be_overwritten"
    )


def _analysis_body(frame_key: str = "1d") -> dict:
    closed_price = 26.48
    return {
        "ok": True,
        "contract": contract_runtime.EXPECTED_CONTRACT,
        "tenant_ids_received": False,
        "frame": {
            "frame_key": frame_key,
            "price": closed_price,
            "closed_candle_price": closed_price,
            "plan_valid": False,
            "targets": [],
        },
        "live_quote_context": {
            "price": 26.55,
            "changes_signal": False,
            "closed_candle_confirmation": True,
            "closed_candle_price_preserved": True,
            "closed_candle_price": closed_price,
        },
        "runtime": _runtime_values(),
    }


def test_remote_analysis_validates_contract_runtime_frame_and_live_safety(
    monkeypatch,
):
    requests_object = _AnalysisRequests(_analysis_body("1d"))
    _patch_bridge(monkeypatch, requests_object)

    result = request_bot_analysis("AAPL", "1d")

    assert result["ok"] is True
    assert requests_object.calls[0][2]["frame"] == "1d"

    requests_object.body = _analysis_body("1h")
    assert request_bot_analysis("AAPL", "1d")["reason"] == "frame_mismatch"

    bad_contract = _analysis_body("1d")
    bad_contract["contract"] = "old-contract"
    requests_object.body = bad_contract
    assert request_bot_analysis("AAPL", "1d")["reason"] == "contract_mismatch"

    missing_runtime = _analysis_body("1d")
    missing_runtime["runtime"] = _runtime_values(installed=False)
    requests_object.body = missing_runtime
    assert request_bot_analysis("AAPL", "1d")["reason"] == "runtime_not_installed"

    wrong_runtime = _analysis_body("1d")
    wrong_runtime["runtime"]["runtime_version"] = "58.0"
    requests_object.body = wrong_runtime
    assert request_bot_analysis("AAPL", "1d")["reason"] == "runtime_version_mismatch"

    unsafe_live = _analysis_body("1d")
    unsafe_live["live_quote_context"]["changes_signal"] = True
    requests_object.body = unsafe_live
    assert request_bot_analysis("AAPL", "1d")["reason"] == "live_quote_may_change_signal"

    mismatched_price = _analysis_body("1d")
    mismatched_price["frame"]["closed_candle_price"] = 26.40
    requests_object.body = mismatched_price
    assert request_bot_analysis("AAPL", "1d")["reason"] == "closed_price_mismatch"


def test_remote_analysis_maps_server_deadlines(monkeypatch):
    requests_object = _AnalysisRequests({}, status_code=504)
    _patch_bridge(monkeypatch, requests_object)

    assert request_bot_analysis("AAPL", "1d") == {
        "ok": False,
        "reason": "analysis_deadline_exceeded",
    }
