"""Backward-compatible access to the canonical Osoli visual system."""
from __future__ import annotations

from styles import apply_custom_css, build_app_css


def build_final_ui_css() -> str:
    """Return the canonical light stylesheet for older tests/imports."""
    return build_app_css("light")


def apply_final_ui_css() -> None:
    """Compatibility alias; new code imports :func:`styles.apply_custom_css`."""
    apply_custom_css()
