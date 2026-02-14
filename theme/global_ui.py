# theme/global_ui.py
"""Global UI helpers for OSOOLI (Streamlit).

Goals:
- Make RTL reliable across Streamlit containers (stApp + sidebar) without breaking code/JSON blocks.
- Keep Streamlit's header visible so the sidebar collapsed-control (hamburger) stays clickable.
- Fix z-index/pointer-events so the collapsed control works even with custom CSS.
"""

from __future__ import annotations

from typing import Optional


def configure_page(title: str, icon: str | None = None) -> None:
    """Call *once* at the very top of app.py before any other Streamlit commands."""
    import streamlit as st

    st.set_page_config(
        page_title=title,
                page_icon=(
            icon
            if (isinstance(icon, str) and icon.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".ico")))
            else (icon if isinstance(icon, str) and len(icon) <= 4 else "📈")
        ),
        layout="wide",
        initial_sidebar_state="expanded",
    )


def apply_global_ui(rtl: bool = True) -> None:
    """Inject minimal, safe CSS for RTL + sidebar controls."""
    import streamlit as st

    dir_css = "rtl" if rtl else "ltr"
    align_css = "right" if rtl else "left"
    # NOTE: Avoid targeting html/body globally. Only scope to Streamlit containers.
    st.markdown(
        f"""
<style>
/* ---------------------------
   RTL: scoped to Streamlit containers only
   --------------------------- */
[data-testid="stAppViewContainer"],
[data-testid="stSidebar"] {{
  direction: {dir_css};
  text-align: {align_css};
}}

/* Keep code/JSON blocks LTR (numbers, code, queries, JSON) */
pre, code,
[data-testid="stCodeBlock"] pre,
[data-testid="stJson"] pre,
[data-testid="stCodeBlock"] pre code,
[data-testid="stJson"] pre code {{
  direction: ltr !important;
  text-align: left !important;
}}

/* ---------------------------
   Sidebar collapsed control must stay clickable
   --------------------------- */
header {{
  display: block !important;
  visibility: visible !important;
  pointer-events: auto !important;
  z-index: 9999 !important;
}}
/* Streamlit uses either stSidebarCollapsedControl or collapsedControl depending on version */
header [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
div[data-testid="stSidebarCollapsedControl"] {{
  display: block !important;
  visibility: visible !important;
  opacity: 1 !important;
  pointer-events: auto !important;
  z-index: 10000 !important;
}}

/* Place the collapsed-control on the right for RTL */
[data-testid="collapsedControl"] {{
  right: 0.75rem !important;
  left: auto !important;
}}

/* Hide the thin resizer line (doesn't affect resizing on most versions) */
[data-testid="stSidebarResizer"] {{
  display: none !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )
