# app.py
import streamlit as st

from styles import apply_global_styles
from views.navbar import render_navbar, get_current_page
from views import router  # existing project router


def main():
    # Page config first
    st.set_page_config(
        page_title="أصولي | Osoli",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Global styles
    apply_global_styles()

    # Navbar (chips style) + query params navigation
    render_navbar()

    # Route based on current page (from query params)
    page = get_current_page()

    # If your project already uses its own router, keep it:
    # We pass `page` down when possible; otherwise fallback to current router behavior.
    try:
        router.route(page=page)
    except TypeError:
        # Older router signature in your repo
        router.route()


if __name__ == "__main__":
    main()
