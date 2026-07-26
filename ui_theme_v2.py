"""Final Arabic RTL design layer for Osoli.

This module is intentionally injected after the legacy stylesheet so current
Streamlit DOM changes cannot silently switch the app back to LTR or replace the
Arabic typeface.
"""
from __future__ import annotations

import textwrap

import streamlit as st


def build_final_ui_css() -> str:
    return textwrap.dedent(
        r"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap');

        :root {
          --os-font-ar: 'Cairo', 'Tahoma', 'Arial', sans-serif;
          --os-surface: var(--card-bg, #ffffff);
          --os-surface-soft: var(--soft-bg, #f8fafc);
          --os-text: var(--txt, #0f172a);
          --os-muted: var(--muted, #64748b);
          --os-primary: var(--primary, #2457e6);
          --os-border: var(--border, rgba(15,23,42,.10));
          --os-border-strong: var(--border2, rgba(15,23,42,.16));
          --os-radius: 16px;
          --os-shadow: 0 10px 30px rgba(15, 23, 42, .07);
        }

        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stSidebar"],
        [data-testid="stVerticalBlock"],
        .block-container {
          direction: rtl !important;
          text-align: right !important;
        }

        html, body, .stApp,
        .stApp p, .stApp li, .stApp label,
        .stApp button, .stApp input, .stApp textarea, .stApp select,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        .stApp [data-testid="stMarkdownContainer"],
        .stApp [data-testid="stMetricLabel"],
        .stApp [data-testid="stMetricValue"],
        [data-baseweb="popover"], [role="listbox"], [role="option"] {
          font-family: var(--os-font-ar) !important;
        }

        /* Preserve Streamlit icon glyphs while restoring Cairo for real text. */
        .material-icons,
        [data-testid="stIconMaterial"] {
          font-family: 'Material Icons' !important;
          direction: ltr !important;
          unicode-bidi: isolate !important;
        }
        .material-symbols-outlined,
        [class*="material-symbols-outlined"] {
          font-family: 'Material Symbols Outlined' !important;
          direction: ltr !important;
          unicode-bidi: isolate !important;
        }
        .material-symbols-rounded,
        [class*="material-symbols-rounded"] {
          font-family: 'Material Symbols Rounded' !important;
          direction: ltr !important;
          unicode-bidi: isolate !important;
        }

        .stApp {
          color: var(--os-text) !important;
          background:
            radial-gradient(circle at 88% 0%, rgba(36,87,230,.08), transparent 30rem),
            radial-gradient(circle at 5% 35%, rgba(14,165,233,.05), transparent 26rem),
            var(--app-bg, #f6f8fb) !important;
          font-size: 15.5px !important;
          line-height: 1.8 !important;
          -webkit-font-smoothing: antialiased;
          text-rendering: optimizeLegibility;
        }

        .block-container {
          max-width: 1500px !important;
          padding-top: 1.35rem !important;
          padding-right: clamp(1rem, 2.2vw, 2.25rem) !important;
          padding-left: clamp(1rem, 2.2vw, 2.25rem) !important;
          padding-bottom: 3rem !important;
        }

        section[data-testid="stSidebar"] {
          right: 0 !important;
          left: auto !important;
          border-left: 1px solid var(--os-border) !important;
          border-right: 0 !important;
          background: color-mix(in srgb, var(--os-surface) 94%, transparent) !important;
          box-shadow: -10px 0 30px rgba(15,23,42,.04) !important;
        }
        section[data-testid="stSidebar"] > div {
          direction: rtl !important;
          text-align: right !important;
          padding: 1.15rem .9rem 1.5rem !important;
        }

        [data-testid="stSidebar"] [role="radiogroup"] {
          gap: .32rem !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
          width: 100% !important;
          min-height: 44px !important;
          padding: .55rem .75rem !important;
          border-radius: 12px !important;
          border: 1px solid transparent !important;
          justify-content: flex-start !important;
          direction: rtl !important;
          transition: background .18s ease, border-color .18s ease, transform .18s ease;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {
          background: rgba(36,87,230,.07) !important;
          border-color: rgba(36,87,230,.13) !important;
          transform: translateX(-2px);
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
          background: linear-gradient(135deg, rgba(36,87,230,.14), rgba(14,165,233,.08)) !important;
          border-color: rgba(36,87,230,.22) !important;
          color: var(--os-primary) !important;
          font-weight: 800 !important;
        }

        .os-app-header {
          direction: rtl !important;
          background:
            linear-gradient(135deg, rgba(36,87,230,.11), rgba(14,165,233,.055)),
            var(--os-surface) !important;
          border: 1px solid var(--os-border-strong) !important;
          border-radius: 20px !important;
          box-shadow: var(--os-shadow) !important;
          padding: 16px 18px !important;
          margin: 0 0 1rem !important;
        }
        .os-app-header .os-h-left {
          flex-direction: row !important;
          direction: rtl !important;
        }
        .os-app-header .os-h-title {
          font-size: 1.42rem !important;
          font-weight: 900 !important;
          letter-spacing: 0 !important;
        }
        .os-app-header .os-h-sub {
          font-size: .9rem !important;
          font-weight: 600 !important;
          color: var(--os-muted) !important;
        }

        .stApp h1, .stApp h2, .stApp h3 {
          color: var(--os-text) !important;
          letter-spacing: 0 !important;
        }
        .stApp h1 { font-size: clamp(1.65rem, 3vw, 2.1rem) !important; font-weight: 900 !important; }
        .stApp h2 { font-size: clamp(1.35rem, 2.4vw, 1.65rem) !important; font-weight: 850 !important; }
        .stApp h3 { font-size: clamp(1.15rem, 2vw, 1.35rem) !important; font-weight: 800 !important; }
        .stApp p, .stApp li { color: var(--os-text) !important; }
        .stApp small, .stApp [data-testid="stCaptionContainer"] { color: var(--os-muted) !important; }

        [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]) {
          direction: ltr !important;
          flex-direction: row-reverse !important;
          gap: .85rem !important;
        }
        [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]) > [data-testid="column"] {
          direction: rtl !important;
          text-align: right !important;
        }

        [data-testid="stForm"],
        [data-testid="stMetric"],
        div[data-testid="stExpander"] details,
        .kpi-card, .stat-card, .os-card, .card {
          background: var(--os-surface) !important;
          border: 1px solid var(--os-border) !important;
          border-radius: var(--os-radius) !important;
          box-shadow: 0 6px 22px rgba(15,23,42,.045) !important;
        }
        [data-testid="stForm"] { padding: 1rem !important; }
        [data-testid="stMetric"] {
          min-height: 112px !important;
          padding: .95rem 1rem !important;
          transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }
        [data-testid="stMetric"]:hover,
        .kpi-card:hover, .stat-card:hover, .os-card:hover {
          transform: translateY(-2px);
          border-color: rgba(36,87,230,.20) !important;
          box-shadow: var(--os-shadow) !important;
        }
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"] {
          width: 100% !important;
          justify-content: flex-start !important;
          text-align: right !important;
        }
        [data-testid="stMetricValue"], [data-testid="stMetricDelta"],
        .td-num, .num, .ticker-symbol, code, pre {
          direction: ltr !important;
          unicode-bidi: isolate !important;
        }
        [data-testid="stMetricValue"] { font-weight: 900 !important; }

        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div,
        [data-testid="stDateInput"] > div > div {
          direction: rtl !important;
          min-height: 46px !important;
          border-radius: 12px !important;
          border-color: var(--os-border-strong) !important;
          background: var(--os-surface) !important;
          box-shadow: none !important;
        }
        .stApp input:not([type="number"]), .stApp textarea,
        [data-baseweb="select"] input,
        [data-baseweb="popover"], [role="listbox"], [role="option"] {
          direction: rtl !important;
          text-align: right !important;
          unicode-bidi: plaintext !important;
        }
        .stApp input[type="number"] {
          direction: ltr !important;
          text-align: right !important;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within {
          border-color: rgba(36,87,230,.55) !important;
          box-shadow: 0 0 0 4px rgba(36,87,230,.11) !important;
        }

        .stButton > button, .stFormSubmitButton > button,
        [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {
          min-height: 44px !important;
          border-radius: 12px !important;
          padding: .55rem 1rem !important;
          font-weight: 800 !important;
          direction: rtl !important;
          transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
        }
        [data-testid="stBaseButton-primary"], .stFormSubmitButton > button {
          background: linear-gradient(135deg, var(--os-primary), #1d78d5) !important;
          border-color: transparent !important;
          color: #fff !important;
          box-shadow: 0 8px 18px rgba(36,87,230,.20) !important;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover {
          transform: translateY(-1px);
          filter: brightness(1.02);
        }

        div[data-testid="stTabs"] { direction: rtl !important; }
        div[data-testid="stTabs"] [role="tablist"] {
          direction: rtl !important;
          flex-direction: row !important;
          justify-content: flex-start !important;
          gap: .4rem !important;
          overflow-x: auto !important;
          padding: .3rem 0 .55rem !important;
        }
        div[data-testid="stTabs"] [role="tab"] {
          min-height: 42px !important;
          padding: .55rem .9rem !important;
          border-radius: 12px !important;
          direction: rtl !important;
          font-weight: 750 !important;
          white-space: nowrap !important;
        }
        div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
          background: rgba(36,87,230,.11) !important;
          color: var(--os-primary) !important;
          box-shadow: inset 0 0 0 1px rgba(36,87,230,.15) !important;
        }

        div[data-testid="stExpander"] details summary {
          direction: rtl !important;
          text-align: right !important;
          min-height: 48px !important;
          padding: .75rem 1rem !important;
          font-weight: 800 !important;
        }
        div[data-testid="stExpander"] details summary > div {
          direction: rtl !important;
          justify-content: flex-start !important;
        }

        [data-testid="stAlert"] {
          direction: rtl !important;
          text-align: right !important;
          border-radius: 14px !important;
          border-width: 1px !important;
          box-shadow: 0 5px 18px rgba(15,23,42,.04) !important;
        }
        [data-testid="stAlert"] > div { direction: rtl !important; text-align: right !important; }

        .finance-table, .os-table, .stApp table {
          direction: rtl !important;
          width: 100% !important;
          border-collapse: separate !important;
          border-spacing: 0 !important;
          overflow: hidden !important;
          border: 1px solid var(--os-border) !important;
          border-radius: 14px !important;
          background: var(--os-surface) !important;
        }
        .finance-table th, .os-table th, .stApp table th {
          text-align: right !important;
          font-weight: 800 !important;
          background: rgba(36,87,230,.07) !important;
        }
        .finance-table td, .finance-table th,
        .os-table td, .os-table th, .stApp table td, .stApp table th {
          padding: .72rem .8rem !important;
          border-bottom: 1px solid var(--os-border) !important;
        }

        [data-testid="stDataFrame"], [data-testid="stTable"] {
          direction: rtl !important;
          border-radius: 14px !important;
          overflow: hidden !important;
          border: 1px solid var(--os-border) !important;
          background: var(--os-surface) !important;
        }

        @media (max-width: 900px) {
          .block-container { padding: .9rem .75rem 2rem !important; }
          .os-app-header { align-items: flex-start !important; padding: 13px 14px !important; }
          .os-app-header .os-h-right { display: none !important; }
          [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]) {
            flex-direction: column !important;
            direction: rtl !important;
            gap: .55rem !important;
          }
          [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]) > [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
          }
        }
        </style>
        """
    ).strip()


def apply_final_ui_css() -> None:
    st.markdown(build_final_ui_css(), unsafe_allow_html=True)
