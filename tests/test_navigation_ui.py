from __future__ import annotations

import inspect

from views import navbar


def test_icon_navigation_uses_compact_hubs_and_no_sidebar():
    expected = {
        "home",
        "insights",
        "portfolios",
        "cash",
        "tools",
        "settings",
    }

    assert set(navbar._NAV_KEYS) == expected
    assert len(navbar._NAV_KEYS) == len(set(navbar._NAV_KEYS))
    assert navbar._PRIMARY_KEYS == navbar._NAV_KEYS
    assert navbar._SECONDARY_KEYS == ()
    assert navbar._ALLOWED == expected | {"update"}
    for removed in (
        "add",
        "analysis",
        "signals",
        "backtest",
        "spec",
        "invest",
        "sukuk",
        "pulse",
    ):
        assert removed not in navbar._NAV_KEYS
    source = inspect.getsource(navbar)
    assert "st.sidebar" not in source
    assert "flex-wrap:nowrap" in source
    assert "st.columns(len(_NAV_KEYS)" in source


def test_legacy_analysis_links_resolve_into_the_analysis_hub():
    for legacy in ("analysis", "signals", "backtest"):
        assert navbar._canonical_page(legacy) == "insights"
        assert navbar._legacy_section(legacy) == legacy
        assert legacy in navbar._ROUTABLE


def test_legacy_portfolio_links_resolve_into_the_portfolios_hub():
    for legacy in ("spec", "invest", "sukuk"):
        assert navbar._canonical_page(legacy) == "portfolios"
        assert navbar._legacy_portfolio_section(legacy) == legacy
        assert legacy in navbar._ROUTABLE


def test_legacy_add_link_opens_embedded_portfolio_entry():
    assert navbar._canonical_page("add") == "portfolios"
    assert "add" in navbar._ROUTABLE
    assert "add" not in navbar._ALLOWED


def test_legacy_pulse_link_opens_owned_stocks_on_home():
    assert navbar._canonical_page("pulse") == "home"
    assert navbar._legacy_home_section("pulse") == "owned_stocks"
    assert "pulse" in navbar._ROUTABLE
    assert navbar._canonical_page("not-a-page") == "home"
    assert navbar._display_page("update") == "home"


def test_every_navigation_tile_has_a_label_icon_and_help_text():
    for key in navbar._NAV_KEYS:
        assert navbar._LABEL_BY_KEY[key].strip()
        assert navbar._SHORT_LABEL_BY_KEY[key].strip()
        assert navbar._ICON_BY_KEY[key].strip()
        assert navbar._HELP_BY_KEY[key].strip()
