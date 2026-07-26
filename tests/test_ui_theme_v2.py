from __future__ import annotations

from ui_theme_v2 import build_final_ui_css


def test_final_theme_restores_cairo_and_global_rtl():
    css = build_final_ui_css()
    assert "'Cairo'" in css
    assert 'direction: rtl !important' in css
    assert '[data-testid="stSidebar"]' in css
    assert '[data-testid="stHorizontalBlock"]:has(> [data-testid="column"])' in css


def test_final_theme_preserves_material_icon_fonts():
    css = build_final_ui_css()
    assert "font-family: 'Material Icons' !important" in css
    assert "font-family: 'Material Symbols Outlined' !important" in css
    assert "font-family: 'Material Symbols Rounded' !important" in css
