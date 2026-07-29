from __future__ import annotations

import inspect

import ai_engine_core
import app
import views
import analysis_header_performance_v7 as header
from views.analysis import financial_v5


def test_performance_runtime_installs_after_router_and_before_analysis_context():
    source = inspect.getsource(app._install_runtime_hardening)
    router = source.index("install_market_data_router()")
    runtime = source.index("install_performance_runtime()")
    context = source.index("install_analysis_context()")
    assert router < runtime < context


def test_ai_reports_use_one_analysis_context():
    source = inspect.getsource(ai_engine_core.generate_ai_report)
    assert "generate_with_context" in source
    assert "raw_generator" in source
    assert "performance" in source


def test_deep_financial_dashboard_is_opt_in_fragment():
    source = inspect.getsource(financial_v5)
    assert "@st.fragment" in source
    toggle = source.index("st.toggle(")
    legacy = source.index("_render_legacy_dashboard(symbol)")
    assert toggle < legacy
    assert "if not enabled" in source


def test_analysis_header_does_not_require_live_network_before_render():
    source = inspect.getsource(header)
    assert "peek_cached_quote" in source
    assert "peek_cached_history" in source
    assert "warm_quote_cache" in source
    assert "fetch_batch_data" not in source


def test_insights_route_uses_performance_wrapper():
    source = inspect.getsource(views._render_page)
    assert '"views.analysis_fast"' in source
