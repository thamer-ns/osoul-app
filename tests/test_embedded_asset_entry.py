from __future__ import annotations

import inspect

import views
from views import asset_entry, navbar, portfolios


def test_sukuk_reference_is_stable_and_never_uses_stock_suffix():
    first = asset_entry._sukuk_reference("", "صكوك الإصدار الأول")
    second = asset_entry._sukuk_reference("", "صكوك الإصدار الأول")
    explicit = asset_entry._sukuk_reference(" sukuk 001 / a ", "اسم")

    assert first == second
    assert first.startswith("SUKUK-")
    assert not first.endswith(".SR")
    assert explicit == "SUKUK-001-A"


def test_each_portfolio_has_one_locked_asset_strategy():
    assert asset_entry._SECTION_STRATEGY == {
        "spec": "مضاربة",
        "invest": "استثمار",
        "sukuk": "صكوك",
    }
    source = inspect.getsource(asset_entry)
    assert "نوع المحفظة محدد مسبقًا" in source
    assert 'asset_type="Stock"' in source
    assert 'asset_type="Sukuk"' in source


def test_portfolios_hub_renders_embedded_entry_before_active_section():
    source = inspect.getsource(portfolios.view_portfolios)
    assert "render_embedded_asset_entry(selected)" in source
    assert source.index("render_embedded_asset_entry(selected)") < source.index(
        "_render_active_section(selected, finance)"
    )


def test_standalone_add_page_is_not_publicly_routed():
    router_source = inspect.getsource(views._render_page)
    assert '"add":' not in router_source
    assert "add" not in navbar._NAV_KEYS
    assert navbar._canonical_page("add") == "portfolios"
    sync_source = inspect.getsource(navbar.sync_page_from_query_params_once)
    assert "pending in _LEGACY_ADD_ROUTES" in sync_source
    assert 'st.session_state["_portfolio_add_open_once"] = True' in inspect.getsource(
        navbar._apply_legacy_destination
    )
