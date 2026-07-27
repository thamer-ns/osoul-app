from __future__ import annotations

from views import navbar


def test_icon_navigation_covers_every_router_destination():
    expected = {
        "home",
        "analysis",
        "spec",
        "invest",
        "sukuk",
        "cash",
        "backtest",
        "pulse",
        "signals",
        "add",
        "tools",
        "settings",
    }

    assert set(navbar._NAV_KEYS) == expected
    assert len(navbar._NAV_KEYS) == len(set(navbar._NAV_KEYS))
    assert navbar._PRIMARY_KEYS[0] == "home"
    assert navbar._ALLOWED == expected | {"update"}


def test_every_navigation_tile_has_a_label_icon_and_help_text():
    for key in navbar._NAV_KEYS:
        assert navbar._LABEL_BY_KEY[key].strip()
        assert navbar._SHORT_LABEL_BY_KEY[key].strip()
        assert navbar._ICON_BY_KEY[key].strip()
        assert navbar._HELP_BY_KEY[key].strip()


def test_transient_update_route_does_not_replace_router_state_with_home():
    assert navbar._validated_page("update") == "update"
    assert navbar._display_page("update") == "home"
    assert navbar._validated_page("not-a-page") == "home"
