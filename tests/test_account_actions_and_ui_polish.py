from __future__ import annotations

import inspect

from ui_polish import build_ui_polish_css
from views import navbar, settings


def test_navigation_has_no_refresh_or_logout_action_strip():
    source = inspect.getsource(navbar)
    assert "nav_refresh" not in source
    assert "nav_logout" not in source
    assert "osoli_nav_actions" not in source
    assert "_logout_callback" not in source
    assert "تحديث الأسعار وتسجيل الخروج" in navbar._HELP_BY_KEY["settings"]


def test_refresh_and_logout_live_inside_settings():
    source = inspect.getsource(settings._render_account_actions)
    assert "settings_refresh_prices" in source
    assert 'navigate_to("update")' in source
    assert "settings_logout" in source
    assert "settings_confirm_logout" in source
    assert "logout_user()" in source


def test_ui_polish_balances_canvas_and_tables():
    css = build_ui_polish_css()
    assert "max-width:1320px" in css
    assert "width:max-content" in css
    assert "min-width:100%" in css
    assert "overflow-x:auto" in css
    assert "white-space:nowrap" in css
    assert "font-size:.78rem" in css
    assert "min-height:98px" in css


def test_ui_polish_keeps_navigation_single_row_on_mobile():
    css = build_ui_polish_css()
    assert ".st-key-osoli_nav_row" in css
    assert "flex-direction:row !important" in css
    assert "min-width:78px" in css
