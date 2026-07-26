from __future__ import annotations

from styles import apply_ui_css, build_app_css
from ui_theme_v2 import build_final_ui_css


def test_canonical_theme_restores_cairo_and_global_rtl():
    css = build_app_css("light")
    assert "'Cairo'" in css
    assert "direction:rtl !important" in css
    assert '[data-testid="stSidebar"]' in css
    assert ".os-h-logo img" in css
    assert "max-height:112px" in css


def test_canonical_theme_avoids_previous_destructive_overrides():
    css = build_app_css("light")
    assert ".stApp *" not in css
    assert "transform:translateX(100%)" not in css
    assert '[data-testid="stTooltipHoverTarget"]' not in css
    assert 'button[title="View fullscreen"]' not in css


def test_streamlit_material_icons_keep_their_native_font():
    css = build_app_css("light")
    assert '[data-testid="stIconMaterial"]' in css
    assert (
        "font-family:'Material Symbols Rounded','Material Symbols Outlined',"
        "'Material Icons' !important"
    ) in css
    assert "keyboard_double_arrow" not in css


def test_legacy_theme_aliases_are_safe():
    assert build_final_ui_css() == build_app_css("light")
    assert apply_ui_css() is None
