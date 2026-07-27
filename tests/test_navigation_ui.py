from __future__ import annotations

import inspect

from views import navbar


def test_icon_navigation_uses_one_compact_row_and_no_sidebar():
    expected = {
        "home",
        "insights",
        "spec",
        "invest",
        "add",
        "sukuk",
        "cash",
        "pulse",
        "tools",
        "settings",
    }

    assert set(navbar._NAV_KEYS) == expected
    assert len(navbar._NAV_KEYS) == len(set(navbar._NAV_KEYS))
    assert navbar._PRIMARY_KEYS == navbar._NAV_KEYS
    assert navbar._SECONDARY_KEYS == ()
    assert navbar._ALLOWED == expected | {"update"}
    assert "analysis" not in navbar._NAV_KEYS
    assert "signals" not in navbar._NAV_KEYS
    assert "backtest" not in navbar._NAV_KEYS
    source = inspect.getsource(navbar)
    assert "st.sidebar" not in source
    assert "flex-wrap:nowrap" in source
    assert "st.columns(len(_NAV_KEYS)" in source


def test_legacy_analysis_links_resolve_into_the_hub():
    for legacy in ("analysis", "signals", "backtest"):
        assert navbar._canonical_page(legacy) == "insights"
        assert navbar._legacy_section(legacy) == legacy
        assert legacy in navbar._ROUTABLE

    assert navbar._canonical_page("not-a-page") == "home"
    assert navbar._display_page("update") == "home"


def test_every_navigation_tile_has_a_label_icon_and_help_text():
    for key in navbar._NAV_KEYS:
        assert navbar._LABEL_BY_KEY[key].strip()
        assert navbar._SHORT_LABEL_BY_KEY[key].strip()
        assert navbar._ICON_BY_KEY[key].strip()
        assert navbar._HELP_BY_KEY[key].strip()
