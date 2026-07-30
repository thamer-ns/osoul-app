from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import global_bot_sync_v8 as sync_runtime


def _reset_runtime_state() -> None:
    with sync_runtime._SYNC_LOCK:  # noqa: SLF001
        sync_runtime._INFLIGHT.clear()  # noqa: SLF001
        sync_runtime._LAST_STARTED.clear()  # noqa: SLF001
        sync_runtime._LAST_COMPLETED.clear()  # noqa: SLF001
        sync_runtime._LAST_RESULT.clear()  # noqa: SLF001


def test_global_sync_never_blocks_streamlit_rerun(monkeypatch) -> None:
    _reset_runtime_state()
    executor = ThreadPoolExecutor(max_workers=1)
    release = threading.Event()
    entered = threading.Event()
    calls: list[int] = []

    def slow_sync(*, limit: int = 100):
        calls.append(limit)
        entered.set()
        release.wait(timeout=2.0)
        return {
            "ok": True,
            "received": 2,
            "cursor": 17,
            "duplicates": 1,
        }

    monkeypatch.setattr(sync_runtime, "_SYNC_EXECUTOR", executor)
    monkeypatch.setattr(sync_runtime, "_MAX_WORKERS", 1)
    monkeypatch.setattr(sync_runtime, "_MIN_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(
        sync_runtime.bridge,
        "bridge_configuration",
        lambda: {"sync_configured": True},
    )
    monkeypatch.setattr(sync_runtime.bridge, "_sync_channel", lambda: "a" * 64)
    monkeypatch.setattr(sync_runtime.bridge, "sync_bot_events", slow_sync)

    try:
        started = time.perf_counter()
        first = sync_runtime.poll_global_bot_sync(now=100.0)
        elapsed = time.perf_counter() - started

        assert elapsed < 0.25
        assert first["pending"] is True
        assert first["scheduled"] is True
        assert first["nonblocking"] is True
        assert entered.wait(timeout=0.5)

        second = sync_runtime.poll_global_bot_sync(now=101.0)
        assert second["pending"] is True
        assert second["scheduled"] is False
        assert calls == [100]

        release.set()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with sync_runtime._SYNC_LOCK:  # noqa: SLF001
                future = sync_runtime._INFLIGHT.get("a" * 64)  # noqa: SLF001
            if future is not None and future.done():
                break
            time.sleep(0.01)

        completed = sync_runtime.poll_global_bot_sync(now=102.0)
        assert completed["pending"] is False
        assert completed["ok"] is True
        assert completed["received"] == 2
        assert completed["duplicates"] == 1
        assert completed["cursor"] == 17
        assert calls == [100]
    finally:
        release.set()
        executor.shutdown(wait=True, cancel_futures=True)
        _reset_runtime_state()


def test_global_sync_has_no_hidden_executor_queue(monkeypatch) -> None:
    _reset_runtime_state()
    executor = ThreadPoolExecutor(max_workers=1)
    release = threading.Event()
    entered = threading.Event()
    channel = {"value": "b" * 64}
    calls = 0

    def slow_sync(*, limit: int = 100):
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=2.0)
        return {"ok": True, "received": 0, "cursor": 0}

    monkeypatch.setattr(sync_runtime, "_SYNC_EXECUTOR", executor)
    monkeypatch.setattr(sync_runtime, "_MAX_WORKERS", 1)
    monkeypatch.setattr(sync_runtime, "_MIN_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(
        sync_runtime.bridge,
        "bridge_configuration",
        lambda: {"sync_configured": True},
    )
    monkeypatch.setattr(
        sync_runtime.bridge,
        "_sync_channel",
        lambda: channel["value"],
    )
    monkeypatch.setattr(sync_runtime.bridge, "sync_bot_events", slow_sync)

    try:
        first = sync_runtime.poll_global_bot_sync(now=200.0)
        assert first["scheduled"] is True
        assert entered.wait(timeout=0.5)

        channel["value"] = "c" * 64
        second = sync_runtime.poll_global_bot_sync(now=200.1)
        assert second["scheduled"] is False
        assert second["pending"] is False
        assert second["reason"] == "sync_capacity_busy"
        assert second["active_workers"] == 1
        assert calls == 1
        with sync_runtime._SYNC_LOCK:  # noqa: SLF001
            assert set(sync_runtime._INFLIGHT) == {"b" * 64}  # noqa: SLF001
    finally:
        release.set()
        executor.shutdown(wait=True, cancel_futures=True)
        _reset_runtime_state()
