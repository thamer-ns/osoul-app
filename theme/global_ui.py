# theme/global_ui.py
"""Global UI helpers for OSOOLI (Streamlit).

Goals:
- Make RTL reliable across Streamlit containers (stApp + sidebar) without breaking code/JSON blocks.
- Keep Streamlit's header visible so the sidebar collapsed-control (hamburger) stays clickable.
- Fix z-index/pointer-events so the collapsed control works even with custom CSS.
"""

from __future__ import annotations


def configure_page(title: str, icon: str | None = None) -> None:
    """Call once near the top of app.py before any other Streamlit commands."""
    import streamlit as st

    # icon: emoji (<=4 chars) or a local image path
    page_icon = "📈"
    if isinstance(icon, str) and icon.strip():
        ic = icon.strip()
        if ic.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".ico")):
            page_icon = ic
        elif len(ic) <= 4:
            page_icon = ic

    st.set_page_config(
        page_title=title,
        page_icon=page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )


def apply_global_ui(rtl: bool = True) -> None:
    """Inject minimal, safe CSS for RTL + sidebar controls."""
    import streamlit as st

    dir_css = "rtl" if rtl else "ltr"
    align_css = "right" if rtl else "left"

    # audit: safe-dynamic-html — values are fixed CSS enums derived from a boolean.
    st.markdown(
        f"""
<style>
/* ============================
   RTL (scoped to Streamlit containers only)
   ============================ */
[data-testid="stAppViewContainer"],
[data-testid="stSidebar"] {{
  direction: {dir_css};
  text-align: {align_css};
}}

/* Keep code/JSON blocks LTR */
pre, code,
[data-testid="stCodeBlock"] pre,
[data-testid="stJson"] pre,
[data-testid="stCodeBlock"] pre code,
[data-testid="stJson"] pre code {{
  direction: ltr !important;
  text-align: left !important;
}}

/* ============================
   Keep sidebar collapsed-control clickable
   ============================ */
header {{
  display: block !important;
  visibility: visible !important;
  pointer-events: auto !important;
  z-index: 9999 !important;
}}
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

/* Hide the thin resizer line (optional) */
[data-testid="stSidebarResizer"] {{
  display: none !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )
