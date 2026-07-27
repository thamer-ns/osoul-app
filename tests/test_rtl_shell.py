from __future__ import annotations

from ui_shell import build_rtl_shell_css


def test_rtl_shell_removes_sidebar_and_open_control():
    css = build_rtl_shell_css()
    assert 'section[data-testid="stSidebar"]' in css
    assert '[data-testid="stSidebarCollapsedControl"]' in css
    assert '[data-testid="collapsedControl"]' in css
    assert "display:none !important" in css
    assert "pointer-events:none !important" in css


def test_rtl_shell_covers_text_surfaces_and_preserves_numeric_islands():
    css = build_rtl_shell_css()
    assert '[data-testid="stMarkdownContainer"]' in css
    assert '[data-testid="stDataFrame"]' in css
    assert '[data-baseweb="popover"]' in css
    assert '[role="dialog"]' in css
    assert "direction:rtl !important" in css
    assert "direction:ltr !important" in css
    assert '[data-testid="stPlotlyChart"]' in css
