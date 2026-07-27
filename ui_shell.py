"""Structural RTL shell for the Streamlit application.

The visual palette remains in :mod:`styles`.  This module owns only two global
layout invariants requested by the product: there is no Streamlit sidebar, and
all text-bearing application surfaces follow Arabic right-to-left flow.
"""
from __future__ import annotations

import textwrap

import streamlit as st


def build_rtl_shell_css() -> str:
    """Return deterministic structural CSS layered after the canonical theme."""
    css = r"""
    <style>
    /* ---------- Permanently remove Streamlit's sidebar shell ---------- */
    section[data-testid="stSidebar"],
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarResizer"] {
      display:none !important;
      visibility:hidden !important;
      opacity:0 !important;
      width:0 !important;
      min-width:0 !important;
      max-width:0 !important;
      pointer-events:none !important;
      overflow:hidden !important;
    }

    [data-testid="stAppViewContainer"] {
      direction:rtl !important;
      flex-direction:row !important;
    }
    [data-testid="stMain"] {
      direction:rtl !important;
      text-align:right !important;
      width:100% !important;
      max-width:100% !important;
      margin:0 !important;
    }

    /* ---------- Arabic RTL for every text-bearing UI surface ---------- */
    html, body, .stApp,
    [data-testid="stMain"],
    [data-testid="stVerticalBlock"],
    [data-testid="stForm"],
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"],
    [data-testid="stWidgetLabel"],
    [data-testid="stAlert"],
    [data-testid="stToast"],
    [data-testid="stFileUploader"],
    [data-testid="stDownloadButton"],
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"],
    [data-testid="stTable"],
    [data-testid="stMetric"],
    [data-testid="stTabs"],
    [data-testid="stRadio"],
    [data-testid="stSelectbox"],
    [data-testid="stMultiSelect"],
    [data-testid="stDateInput"],
    [data-testid="stNumberInput"],
    [data-testid="stTextInput"],
    [data-testid="stTextArea"],
    [data-baseweb="select"],
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [role="dialog"],
    [role="listbox"],
    [role="option"],
    [role="menuitem"] {
      direction:rtl !important;
      text-align:right !important;
    }

    .stApp h1, .stApp h2, .stApp h3,
    .stApp h4, .stApp h5, .stApp h6,
    .stApp p, .stApp li, .stApp label,
    .stApp summary, .stApp button,
    .stApp [role="tab"],
    .stApp [data-testid="stNotificationContentInfo"],
    .stApp [data-testid="stNotificationContentWarning"],
    .stApp [data-testid="stNotificationContentError"],
    .stApp [data-testid="stNotificationContentSuccess"] {
      direction:rtl !important;
      text-align:right !important;
      unicode-bidi:plaintext !important;
    }

    [data-testid="stHorizontalBlock"],
    [data-testid="stColumns"],
    [data-testid="stTabs"] [role="tablist"],
    [data-testid="stRadio"] [role="radiogroup"] {
      direction:rtl !important;
      flex-direction:row !important;
    }

    [data-baseweb="popover"] > div,
    [data-baseweb="menu"] > div,
    [role="dialog"] > div,
    div[data-testid="stExpander"] details,
    div[data-testid="stExpander"] details summary {
      direction:rtl !important;
      text-align:right !important;
    }

    .stApp table,
    .stApp table th,
    .stApp table td,
    .finance-table,
    .finance-table th,
    .finance-table td,
    .os-table,
    .os-table th,
    .os-table td {
      direction:rtl !important;
      text-align:right !important;
    }

    /* ---------- Legitimate LTR islands inside the Arabic interface ---------- */
    pre, code,
    [data-testid="stCodeBlock"],
    [data-testid="stJson"],
    [data-testid="stPlotlyChart"],
    .js-plotly-plot,
    .plot-container,
    .svg-container,
    .ticker-symbol,
    .td-num,
    .num,
    input[type="number"],
    input[type="tel"] {
      direction:ltr !important;
      unicode-bidi:isolate !important;
    }

    pre, code,
    [data-testid="stCodeBlock"],
    [data-testid="stJson"] {
      text-align:left !important;
    }

    .ticker-symbol, .td-num, .num,
    input[type="number"], input[type="tel"] {
      text-align:right !important;
      font-variant-numeric:tabular-nums;
    }
    </style>
    """
    return textwrap.dedent(css).strip()


def apply_rtl_shell() -> None:
    """Inject the structural shell after the canonical visual theme."""
    st.markdown(build_rtl_shell_css(), unsafe_allow_html=True)
