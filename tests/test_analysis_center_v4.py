from __future__ import annotations

import inspect

from ai_engine_core.compass_contract import compare_compass_with_report
from views import insights
from views.analysis import TIMEFRAME_OPTIONS
from views.analysis import advisor
from views.analysis import integration_v5
from views.analysis import overview
from views.analysis import overview_v4
from views.analysis import overview_v5


def test_analysis_hub_contains_evaluation_and_four_lazy_sections():
    assert insights._SECTION_KEYS == ("analysis", "signals", "backtest", "evaluation")
    assert insights._SECTION_META["evaluation"]["module"] == "views.analysis.evaluation"
    source = inspect.getsource(insights)
    assert "st.columns(len(_SECTION_KEYS)" in source
    assert "importlib.import_module" in source


def test_analysis_workspace_supports_every_compass_timeframe():
    assert set(TIMEFRAME_OPTIONS.values()) == {
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
        "1d",
        "1wk",
        "1mo",
    }


def test_unified_overview_is_explicit_run_and_external_compass_never_overrides():
    source = inspect.getsource(overview_v4.render_unified_overview)
    module_source = inspect.getsource(overview_v4)
    assert "تشغيل التحليل الموحد" in source
    assert "if run or refresh" in source
    assert "compare_compass_with_report" in module_source

    comparison = compare_compass_with_report(
        {
            "symbol": "1120.SR",
            "timeframe": "1d",
            "direction": "buy",
            "geometry": {"valid": True},
        },
        {
            "symbol": "1120.SR",
            "direction": "sell",
            "analysis_contract": {"timeframe": "1d"},
        },
    )
    assert comparison["aligned"] is False
    assert comparison["decision_effect"] == "none"


def test_advisor_route_no_longer_exposes_raw_stack_traces():
    source = inspect.getsource(advisor)
    assert "__trace__" not in source
    assert "st.code" not in source
    assert "advisor_v5" in source


def test_compatibility_overview_route_points_to_v5_integration():
    route_source = inspect.getsource(overview)
    wrapper_source = inspect.getsource(overview_v5)
    integration_source = inspect.getsource(integration_v5)
    assert "overview_v5" in route_source
    assert "render_integration_workspace" in wrapper_source
    assert "record_external_event" in integration_source
    assert "forward_compass_payload" in integration_source
