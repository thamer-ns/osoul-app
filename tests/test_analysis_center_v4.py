from __future__ import annotations

import inspect

from views import insights
from views.analysis import TIMEFRAME_OPTIONS
from views.analysis import advisor
from views.analysis import overview
from views.analysis import overview_v4


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
    source = inspect.getsource(overview.render_unified_overview)
    module_source = inspect.getsource(overview_v4)
    assert "تشغيل التحليل الموحد" in source
    assert "if run or refresh" in source
    assert "compare_compass_with_report" in module_source
    assert "ولا يغيّر الدليل الخارجي قرار أصولي تلقائيًا" in module_source


def test_advisor_route_no_longer_exposes_raw_stack_traces():
    source = inspect.getsource(advisor)
    assert "__trace__" not in source
    assert "st.code" not in source
    assert "advisor_v4" in source


def test_compatibility_overview_route_points_to_hardened_module():
    source = inspect.getsource(overview)
    assert "overview_v4" in source
