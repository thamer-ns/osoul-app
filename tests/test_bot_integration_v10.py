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


def test_cache_resilience_installs_before_sc_runtime_and_contract_after():
    source = inspect.getsource(routes)

    assert source.index("install_persistent_cache_resilience_v10()") < source.index(
        "from sc_runtime_v8 import install_sc_runtime_v8"
    )
    assert source.index("install_sc_runtime_v8()") < source.index(
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
        "runtime": {
            "installed": installed,
            "feature_version": "55.0",
        },
    }


def test_runtime_probe_requires_live_v55_engine(monkeypatch):
    requests_object = _RuntimeRequests(_runtime_body())
    _patch_bridge(monkeypatch, requests_object)

    result = contract_runtime._probe_runtime()

    assert result["ok"] is True
    assert result["contract"] == contract_runtime.EXPECTED_CONTRACT
    assert result["remote_analysis"] is True
    assert result["runtime_installed"] is True
    assert result["endpoint"] == "/integrations/osoli/runtime"
    assert len(requests_object.calls) == 1


def test_runtime_probe_rejects_uninstalled_or_wrong_contract(monkeypatch):
    requests_object = _RuntimeRequests(_runtime_body(installed=False))
    _patch_bridge(monkeypatch, requests_object)
    assert contract_runtime._probe_runtime()["reason"] == "runtime_not_installed"

    requests_object.body = _runtime_body(contract="old-contract")
    assert contract_runtime._probe_runtime()["reason"] == "contract_mismatch"


def _analysis_body(frame_key: str = "1d") -> dict:
    return {
        "ok": True,
        "contract": contract_runtime.EXPECTED_CONTRACT,
        "tenant_ids_received": False,
        "frame": {
            "frame_key": frame_key,
            "plan_valid": False,
            "targets": [],
        },
        "runtime": {
            "installed": True,
            "feature_version": "55.0",
        },
    }


def test_remote_analysis_validates_contract_runtime_and_frame(monkeypatch):
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
    missing_runtime["runtime"] = {"installed": False, "feature_version": "55.0"}
    requests_object.body = missing_runtime
    assert request_bot_analysis("AAPL", "1d")["reason"] == "runtime_not_installed"


def test_remote_analysis_maps_server_deadlines(monkeypatch):
    requests_object = _AnalysisRequests({}, status_code=504)
    _patch_bridge(monkeypatch, requests_object)

    assert request_bot_analysis("AAPL", "1d") == {
        "ok": False,
        "reason": "analysis_deadline_exceeded",
    }
