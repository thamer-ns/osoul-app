from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import app
from ai_engine_core import external_signal_journal_v5 as journal


def _fake_streamlit() -> SimpleNamespace:
    return SimpleNamespace(session_state={})


def test_optional_runtime_stage_degrades_without_blocking(monkeypatch) -> None:
    fake = _fake_streamlit()
    monkeypatch.setattr(app, "st", fake)

    def fail() -> None:
        raise PermissionError("optional provider unavailable")

    assert app._run_runtime_stage("optional_feature", fail, critical=False) is False
    assert fake.session_state["_runtime_optional_failures"] == ["optional_feature"]
    assert "_tenant_init_stage" not in fake.session_state

    assert app._run_runtime_stage("optional_feature", lambda: None, critical=False) is True
    assert fake.session_state["_runtime_optional_failures"] == []


def test_security_critical_runtime_stage_fails_closed(monkeypatch) -> None:
    fake = _fake_streamlit()
    monkeypatch.setattr(app, "st", fake)

    with pytest.raises(RuntimeError):
        app._run_runtime_stage(
            "tenant_scope",
            lambda: (_ for _ in ()).throw(RuntimeError("scope unavailable")),
            critical=True,
        )

    assert fake.session_state["_tenant_init_stage"] == "tenant_scope"


def test_runtime_bootstrap_keeps_optional_failures_outside_tenant_gate(monkeypatch) -> None:
    fake = _fake_streamlit()
    monkeypatch.setattr(app, "st", fake)
    calls: list[tuple[str, str, tuple[object, ...]]] = []

    def invoke(module_name: str, function_name: str, *args: object) -> None:
        calls.append((module_name, function_name, args))
        if function_name in {
            "install_external_signal_journal",
            "install_analysis_routes",
        }:
            raise RuntimeError("optional runtime unavailable")

    monkeypatch.setattr(app, "_invoke_runtime", invoke)

    app._install_runtime_hardening("alice")

    assert (
        "tenant_scope",
        "install_tenant_scope",
        ("alice",),
    ) in calls
    assert (
        "ai_tenant_hardening",
        "install_ai_learning_scope",
        (),
    ) in calls
    assert fake.session_state["_runtime_optional_failures"] == [
        "external_signal_journal",
        "analysis_routes",
    ]
    tenant_index = next(
        index
        for index, item in enumerate(calls)
        if item[1] == "install_tenant_scope"
    )
    route_index = next(
        index
        for index, item in enumerate(calls)
        if item[1] == "install_analysis_routes"
    )
    assert tenant_index < route_index


def test_runtime_bootstrap_still_blocks_unverified_tenant(monkeypatch) -> None:
    fake = _fake_streamlit()
    monkeypatch.setattr(app, "st", fake)

    def invoke(module_name: str, function_name: str, *args: object) -> None:
        _ = module_name, args
        if function_name == "install_tenant_scope":
            raise RuntimeError("tenant schema unavailable")

    monkeypatch.setattr(app, "_invoke_runtime", invoke)

    with pytest.raises(RuntimeError):
        app._install_runtime_hardening("alice")

    assert fake.session_state["_tenant_init_stage"] == "tenant_scope"


def test_external_journal_install_failure_is_read_safe_and_write_closed(
    monkeypatch,
) -> None:
    def fail_install() -> None:
        raise PermissionError("DDL denied")

    monkeypatch.setattr(journal._impl, "install_external_signal_journal", fail_install)
    monkeypatch.setattr(
        journal._impl,
        "latest_external_event",
        lambda *_args, **_kwargs: pytest.fail("unsafe journal read executed"),
    )
    monkeypatch.setattr(
        journal._impl,
        "latest_remote_cursor",
        lambda *_args, **_kwargs: pytest.fail("unsafe cursor read executed"),
    )

    journal.install_external_signal_journal()
    assert journal.latest_external_event("2222", "1d") is None
    assert journal.latest_remote_cursor("a" * 64) == 0

    snapshot = journal.lifecycle_snapshot("2222", "1d")
    assert snapshot["available"] is False
    assert snapshot["migration_warning"] == "journal_install_failed"

    recent = journal.recent_external_events("2222", "1d")
    quarantined = journal.recent_quarantined_events()
    assert isinstance(recent, pd.DataFrame) and recent.empty
    assert isinstance(quarantined, pd.DataFrame) and quarantined.empty
    assert recent.attrs["journal_unavailable_reason"] == "journal_install_failed"

    write = journal.record_external_event({"source": "SC-V91", "event": "NL"})
    assert write["ok"] is False
    assert write["reason"] == "legacy_migration_unavailable"
    assert write["migration_reason"] == "journal_install_failed"


def test_external_journal_migration_exception_is_contained(monkeypatch) -> None:
    monkeypatch.setattr(
        journal._impl,
        "install_external_signal_journal",
        lambda: None,
    )
    monkeypatch.setattr(
        journal,
        "migrate_current_tenant_v6_to_v7",
        lambda: (_ for _ in ()).throw(RuntimeError("migration outage")),
    )

    result = journal._prepare()

    assert result == {
        "ok": False,
        "reason": "migration_failed",
        "migrated": 0,
    }
