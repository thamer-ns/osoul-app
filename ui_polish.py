"""Final responsive density and readability layer for Osoli."""
from __future__ import annotations

import textwrap

import streamlit as st


def build_ui_polish_css() -> str:
    css = r"""
    <style>
    /* Balanced desktop canvas: neither edge-to-edge nor cramped. */
    .block-container {
      width:100% !important;
      max-width:1320px !important;
      padding:.72rem clamp(.72rem,1.45vw,1.28rem) 2.2rem !important;
      margin-inline:auto !important;
    }

    .stApp {
      font-size:14px !important;
      line-height:1.62 !important;
    }
    .stApp h1 { font-size:clamp(1.48rem,2.1vw,1.78rem) !important; }
    .stApp h2 { font-size:clamp(1.26rem,1.8vw,1.5rem) !important; }
    .stApp h3 { font-size:clamp(1.08rem,1.45vw,1.24rem) !important; }
    .stApp p, .stApp li { line-height:1.68 !important; }
    .stApp [data-testid="stCaptionContainer"] { font-size:.77rem !important; }

    /* Compact, clearer application header. */
    .os-app-header {
      min-height:68px !important;
      max-height:88px !important;
      padding:.62rem .78rem !important;
      margin:0 0 .55rem !important;
      border-radius:17px !important;
      gap:.72rem !important;
      box-shadow:0 7px 23px rgba(15,23,42,.065) !important;
    }
    .os-h-logo {
      width:46px !important;
      height:46px !important;
      min-width:46px !important;
      max-width:46px !important;
      border-radius:12px !important;
    }
    .os-h-logo img { max-width:46px !important; max-height:46px !important; }
    .os-h-title { font-size:1.16rem !important; }
    .os-h-sub { font-size:.78rem !important; margin-top:.1rem !important; }
    .os-h-right { gap:.3rem !important; }
    .os-chip { min-height:27px !important; padding:.18rem .5rem !important; font-size:.72rem !important; }

    /* Navigation remains a single row, without the old action strip. */
    .st-key-osoli_icon_navigation {
      padding:.3rem .34rem !important;
      margin:.05rem 0 .48rem !important;
      border-radius:13px !important;
      box-shadow:0 4px 15px rgba(15,23,42,.04) !important;
    }
    .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] {
      gap:.24rem !important;
      padding:0 !important;
    }
    .st-key-osoli_nav_row .stButton > button {
      min-height:40px !important;
      height:40px !important;
      padding:.2rem .15rem !important;
      border-radius:9px !important;
      font-size:.72rem !important;
      gap:.18rem !important;
    }
    .st-key-osoli_nav_row .stButton > button p { font-size:.72rem !important; }
    .st-key-osoli_nav_row .stButton > button [data-testid="stIconMaterial"] {
      font-size:.88rem !important;
      min-width:.88rem !important;
    }

    /* Forms, controls, tabs and expanders. */
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div,
    [data-testid="stDateInput"] > div > div {
      min-height:41px !important;
    }
    .stButton > button,
    .stFormSubmitButton > button,
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-secondary"] {
      min-height:40px !important;
      padding:.42rem .72rem !important;
      border-radius:10px !important;
      font-size:.82rem !important;
    }
    [data-testid="stForm"] { padding:.82rem !important; }
    [data-testid="stTabs"] [role="tab"] {
      min-height:37px !important;
      padding:.38rem .68rem !important;
      font-size:.8rem !important;
    }
    div[data-testid="stExpander"] details summary {
      min-height:43px !important;
      padding:.56rem .72rem !important;
      font-size:.84rem !important;
    }

    /* KPI and dashboard cards. */
    [data-testid="stHorizontalBlock"], [data-testid="stColumns"] {
      gap:.62rem !important;
    }
    [data-testid="stMetric"] {
      min-height:94px !important;
      padding:.68rem .76rem !important;
      border-radius:13px !important;
    }
    [data-testid="stMetricLabel"] { font-size:.76rem !important; }
    [data-testid="stMetricValue"] { font-size:1.25rem !important; }
    .kpi-card {
      min-height:98px !important;
      padding:.7rem .78rem !important;
      border-radius:13px !important;
    }
    .kpi-icon-bg { font-size:1rem !important; margin-bottom:.3rem !important; }
    .kpi-label { font-size:.76rem !important; }
    .kpi-value { font-size:1.24rem !important; margin-top:.12rem !important; }
    .tasi-card {
      min-height:100px !important;
      padding:.78rem .9rem !important;
      border-radius:14px !important;
    }
    .os-card { padding:.78rem !important; margin:.34rem 0 !important; border-radius:13px !important; }
    .os-card-title { font-size:.93rem !important; margin-bottom:.5rem !important; }
    .os-kv { padding:.38rem 0 !important; gap:.65rem !important; }

    /* Tables keep readable columns and scroll instead of being squeezed. */
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"],
    [data-testid="stTable"],
    .element-container:has(.finance-table),
    .element-container:has(.os-table),
    .element-container:has(table) {
      width:100% !important;
      max-width:100% !important;
      overflow-x:auto !important;
      overflow-y:hidden !important;
      border-radius:11px !important;
    }
    .finance-table, .os-table, .stApp table {
      width:max-content !important;
      min-width:100% !important;
      max-width:none !important;
      font-size:.78rem !important;
      table-layout:auto !important;
    }
    .finance-table td, .finance-table th,
    .os-table td, .os-table th,
    .stApp table td, .stApp table th {
      padding:.46rem .54rem !important;
      line-height:1.35 !important;
      white-space:nowrap !important;
    }
    .finance-table th, .os-table th, .stApp table th {
      font-size:.75rem !important;
      position:sticky !important;
      top:0 !important;
      z-index:1 !important;
    }
    [data-testid="stDataFrame"] *, [data-testid="stDataEditor"] * {
      font-size:.78rem !important;
    }

    .os-auth-loading {
      max-width:520px !important;
      margin:15vh auto 0 !important;
      padding:1rem 1.1rem !important;
      text-align:center !important;
      color:var(--os-muted) !important;
      font-weight:750 !important;
      border:1px solid var(--os-border) !important;
      border-radius:14px !important;
      background:var(--os-surface) !important;
      box-shadow:0 8px 24px rgba(15,23,42,.055) !important;
    }

    @media (min-width:721px) and (max-width:900px) {
      [data-testid="stHorizontalBlock"], [data-testid="stColumns"] {
        flex-direction:row !important;
      }
      [data-testid="stHorizontalBlock"] > [data-testid="column"],
      [data-testid="stColumns"] > [data-testid="column"] {
        width:auto !important;
        flex:1 1 0 !important;
      }
      .os-h-right { display:flex !important; }
    }

    @media (max-width:720px) {
      .block-container { padding:.55rem .48rem 1.7rem !important; }
      [data-testid="stHorizontalBlock"], [data-testid="stColumns"] {
        flex-direction:column !important;
        gap:.46rem !important;
      }
      [data-testid="stHorizontalBlock"] > [data-testid="column"],
      [data-testid="stColumns"] > [data-testid="column"] {
        width:100% !important;
        flex:1 1 100% !important;
      }
      .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] {
        flex-direction:row !important;
      }
      .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        width:auto !important;
        min-width:78px !important;
        flex:0 0 78px !important;
      }
      .os-app-header { min-height:64px !important; padding:.55rem .62rem !important; }
      .os-h-logo { width:42px !important; height:42px !important; min-width:42px !important; max-width:42px !important; }
      .os-h-logo img { max-width:42px !important; max-height:42px !important; }
      .os-h-title { font-size:1.04rem !important; }
      .os-h-sub { font-size:.72rem !important; }
      .os-h-right { display:none !important; }
    }
    </style>
    """
    return textwrap.dedent(css).strip()


def apply_ui_polish() -> None:
    st.markdown(build_ui_polish_css(), unsafe_allow_html=True)
