from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import analysis_header_performance_v7 as header
import analysis_routes_v5 as routes
import views
from streamlit.testing.v1 import AppTest
from views import analysis_fast, insights
from views.analysis import workspace_v18, workspace_v20


def test_analysis_hub_has_exactly_two_user_sections() -> None:
    assert insights._SECTION_KEYS == ("analysis", "evaluation")
    assert set(insights._SECTION_META) == {"analysis", "evaluation"}
    assert insights._normalize_section("signals") == "analysis"
    assert insights._normalize_section("backtest") == "evaluation"
    assert insights._SECTION_META["analysis"]["module"] == "views.analysis_fast"


def test_analysis_runtime_attempt_is_fail_open() -> None:
    failures: list[str] = []

    routes._attempt(
        "market_integrity",
        lambda: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        failures,
    )

    assert failures == ["market_integrity"]


def test_analysis_runtime_status_exposes_two_sections(monkeypatch) -> None:
    monkeypatch.setattr(routes, "_INSTALLED", True)
    monkeypatch.setattr(routes, "_FAILURES", ["live_report"])

    status = routes.runtime_status()

    assert status["installed"] is True
    assert status["analysis_entry_independent"] is True
    assert status["failed_components"] == ["live_report"]
    assert status["user_sections"] == ["analysis", "evaluation"]


def test_header_acceleration_falls_back_when_cache_raises(monkeypatch) -> None:
    original_calls: list[str] = []
    module = SimpleNamespace(
        get_ticker_symbol=lambda symbol: symbol,
        normalize_symbol=lambda symbol: symbol,
        _price_snapshot=lambda symbol: (
            original_calls.append(symbol)
            or {
                "price": 26.5,
                "source": "original",
                "is_stale": False,
            }
        ),
    )
    monkeypatch.setattr(header, "_INSTALLED_MODULES", set())
    monkeypatch.setattr(
        header,
        "peek_cached_quote",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("cache unavailable")
        ),
    )
    monkeypatch.setattr(header, "record_phase", lambda *_args, **_kwargs: None)

    header.install_analysis_header_performance(module)
    snapshot = module._price_snapshot("2222.SR")

    assert snapshot["price"] == 26.5
    assert snapshot["source"] == "original"
    assert original_calls == ["2222.SR"]


def test_fast_wrapper_calls_current_entry_without_legacy_routes(monkeypatch) -> None:
    calls: list[object] = []
    module = ModuleType("views.analysis")
    module.view_analysis = lambda finance: calls.append(finance)  # type: ignore[attr-defined]
    module.get_ticker_symbol = lambda symbol: symbol  # type: ignore[attr-defined]
    module.normalize_symbol = lambda symbol: symbol  # type: ignore[attr-defined]
    module._price_snapshot = lambda _symbol: {}  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "views.analysis", module)
    monkeypatch.setattr(views, "analysis", module, raising=False)
    monkeypatch.setattr(
        header,
        "install_analysis_header_performance",
        lambda installed: calls.append(installed),
    )

    finance = {"portfolio_value": 100_000.0}
    analysis_fast.view_analysis(finance)

    assert calls == [module, finance]


def test_generation_failure_is_contained(monkeypatch) -> None:
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setattr(workspace_v18, "st", fake_st)
    monkeypatch.setattr(workspace_v20, "st", fake_st)
    monkeypatch.setattr(
        workspace_v20,
        "_generate_ai_report_flex",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("provider outage")
        ),
    )

    payload = workspace_v20._generate("2222.SR", "1d", refresh=True)
    report = payload["report"]

    assert report["ok"] is False
    assert report["diagnostic_code"] == "analysis_generation_failed"
    assert "صفقة" in report["message"]


def test_streamlit_analysis_hub_opens_without_runtime_exception() -> None:
    app = AppTest.from_string(
        "from views.insights import view_insights\n"
        "view_insights({})\n"
    )
    app.run(timeout=30)

    assert not app.exception
    visible = "\n".join(
        str(item.value)
        for collection in (app.markdown, app.caption, app.header, app.info)
        for item in collection
    )
    assert "مركز التحليل والقرار" in visible
    assert "التحليل الشامل" in visible
