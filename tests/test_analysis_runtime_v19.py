from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import analysis_header_performance_v7 as header
import analysis_routes_v5 as routes
import views
from views import analysis_fast


def test_route_upgrade_accepts_v18_workspace_without_legacy_tabs() -> None:
    workspace = SimpleNamespace(view_analysis=lambda _finance: None)
    routes._install_legacy_section_routes(workspace)
    assert not hasattr(workspace, "SECTION_ROUTES")


def test_route_upgrade_still_supports_warm_legacy_workspace() -> None:
    workspace = SimpleNamespace(
        view_analysis=lambda _finance: None,
        SECTION_ROUTES={},
    )
    routes._install_legacy_section_routes(workspace)
    assert "💰 التحليل المالي" in workspace.SECTION_ROUTES
    assert "🤖 تحليل البوت" in workspace.SECTION_ROUTES


def test_header_acceleration_does_not_require_retired_safe_renderer(
    monkeypatch,
) -> None:
    module = SimpleNamespace(
        get_ticker_symbol=lambda symbol: symbol,
        normalize_symbol=lambda symbol: symbol,
        _price_snapshot=lambda _symbol: {},
    )
    header._INSTALLED_MODULES.clear()
    monkeypatch.setattr(
        header,
        "peek_cached_quote",
        lambda *_args, **_kwargs: {
            "price": 26.5,
            "prev_close": 26.0,
            "source": "sahmk",
            "fetched_at": "now",
            "is_stale": False,
        },
    )
    monkeypatch.setattr(header, "record_phase", lambda *_args, **_kwargs: None)

    header.install_analysis_header_performance(module)

    snapshot = module._price_snapshot("2222.SR")
    assert snapshot["price"] == 26.5
    assert snapshot["source"] == "sahmk"
    assert not hasattr(module, "_safe_render")


def test_fast_wrapper_calls_v18_entry_without_section_routes(monkeypatch) -> None:
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
