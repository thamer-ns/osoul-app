"""Canonical Osoli visual system.

The application previously injected several large and contradictory style sheets.
This module is now the single source of truth for the Streamlit layout, Arabic
RTL behaviour, component sizing and responsive design.
"""
from __future__ import annotations

import textwrap

import streamlit as st


def _theme_name() -> str:
    try:
        value = str(st.session_state.get("ui_theme") or "light").strip().lower()
    except Exception:
        value = "light"
    return value if value in {"light", "dark"} else "light"


def build_app_css(theme: str = "light") -> str:
    """Return the complete deterministic stylesheet used by the app."""
    dark = str(theme).strip().lower() == "dark"
    palette = (
        """
        --os-bg:#07111f;
        --os-surface:#0d1828;
        --os-surface-soft:#101e31;
        --os-text:#e8eef8;
        --os-muted:#9cabc0;
        --os-border:rgba(148,163,184,.18);
        --os-border-strong:rgba(148,163,184,.30);
        --os-shadow:0 12px 34px rgba(0,0,0,.28);
        --os-row-alt:rgba(255,255,255,.025);
        --os-hover:rgba(96,165,250,.10);
        """
        if dark
        else
        """
        --os-bg:#f4f7fb;
        --os-surface:#ffffff;
        --os-surface-soft:#f8fafc;
        --os-text:#10203a;
        --os-muted:#64748b;
        --os-border:rgba(15,23,42,.10);
        --os-border-strong:rgba(15,23,42,.17);
        --os-shadow:0 12px 34px rgba(15,23,42,.075);
        --os-row-alt:rgba(15,23,42,.018);
        --os-hover:rgba(37,99,235,.065);
        """
    )

    css = r"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap');

    :root {
      __PALETTE__
      --os-primary:#2457e6;
      --os-primary-2:#0e8fca;
      --os-success:#059669;
      --os-danger:#dc2626;
      --os-warning:#d97706;
      --os-info:#2563eb;
      --os-font:'Cairo','Tahoma','Arial',sans-serif;
      --os-radius-xs:9px;
      --os-radius-sm:12px;
      --os-radius-md:16px;
      --os-radius-lg:21px;
      --os-focus:0 0 0 4px rgba(36,87,230,.12);
    }

    /* ---------- Root direction and page geometry ---------- */
    html, body, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stSidebar"],
    [data-testid="stVerticalBlock"],
    [data-testid="stForm"],
    .block-container {
      direction:rtl !important;
      text-align:right !important;
    }

    html, body { background:var(--os-bg) !important; }

    .stApp {
      background:
        radial-gradient(circle at 92% -5%, rgba(36,87,230,.085), transparent 29rem),
        radial-gradient(circle at 5% 42%, rgba(14,143,202,.05), transparent 26rem),
        var(--os-bg) !important;
      color:var(--os-text) !important;
      font-family:var(--os-font) !important;
      font-size:15px !important;
      line-height:1.72 !important;
      overflow-x:hidden !important;
      -webkit-font-smoothing:antialiased;
      text-rendering:optimizeLegibility;
    }

    /* Set RTL flow once. Do not reverse nested Streamlit internals. */
    [data-testid="stAppViewContainer"] {
      direction:rtl !important;
      flex-direction:row !important;
    }

    [data-testid="stMain"] { min-width:0 !important; }

    .block-container {
      width:100% !important;
      max-width:1480px !important;
      padding:1.1rem clamp(.85rem,2.1vw,2.1rem) 3rem !important;
      margin-inline:auto !important;
    }

    /* ---------- Typography: target text, never Streamlit icon glyphs ---------- */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stApp p, .stApp li, .stApp label,
    .stApp input, .stApp textarea, .stApp select,
    .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stCaptionContainer"],
    .stApp [role="tab"], .stApp [role="option"],
    [data-baseweb="popover"], [data-baseweb="menu"] {
      font-family:var(--os-font) !important;
    }

    .stApp h1, .stApp h2, .stApp h3,
    .stApp h4, .stApp h5, .stApp h6 {
      color:var(--os-text) !important;
      letter-spacing:0 !important;
      text-align:right !important;
      margin-top:.55rem !important;
    }
    .stApp h1 { font-size:clamp(1.65rem,2.8vw,2.15rem) !important; font-weight:900 !important; line-height:1.28 !important; }
    .stApp h2 { font-size:clamp(1.35rem,2.3vw,1.72rem) !important; font-weight:850 !important; line-height:1.34 !important; }
    .stApp h3 { font-size:clamp(1.14rem,1.9vw,1.38rem) !important; font-weight:800 !important; line-height:1.38 !important; }
    .stApp p, .stApp li { color:var(--os-text) !important; line-height:1.82 !important; }
    .stApp small, .stApp [data-testid="stCaptionContainer"], .os-muted { color:var(--os-muted) !important; }
    .stApp a { color:var(--os-primary) !important; font-weight:700 !important; text-decoration:none !important; }
    .stApp a:hover { text-decoration:underline !important; }

    /* Let Streamlit's bundled icon font remain untouched. */
    [data-testid="stIconMaterial"],
    [data-testid="stIconMaterial"] * {
      font-family:'Material Symbols Rounded','Material Symbols Outlined','Material Icons' !important;
      font-weight:normal !important;
      font-style:normal !important;
      letter-spacing:normal !important;
      text-transform:none !important;
      white-space:nowrap !important;
      word-wrap:normal !important;
      direction:ltr !important;
      unicode-bidi:isolate !important;
      font-feature-settings:'liga' !important;
      -webkit-font-feature-settings:'liga' !important;
      -webkit-font-smoothing:antialiased !important;
    }
    svg, [role="img"] { direction:ltr !important; unicode-bidi:isolate !important; }

    pre, code, [data-testid="stCodeBlock"], [data-testid="stJson"] {
      direction:ltr !important;
      text-align:left !important;
      unicode-bidi:isolate !important;
      font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace !important;
    }

    /* ---------- Streamlit chrome ---------- */
    header[data-testid="stHeader"] {
      background:transparent !important;
      border:0 !important;
      pointer-events:none !important;
    }
    header[data-testid="stHeader"] button,
    header[data-testid="stHeader"] a,
    [data-testid="stSidebarCollapsedControl"] {
      pointer-events:auto !important;
    }
    [data-testid="stToolbar"],
    [data-testid="stToolbarActions"],
    [data-testid="stHeaderActionElements"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    .stAppDeployButton {
      display:none !important;
    }
    #MainMenu, footer { visibility:hidden !important; }

    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
      position:fixed !important;
      top:.72rem !important;
      right:.72rem !important;
      left:auto !important;
      z-index:10020 !important;
    }
    [data-testid="stSidebarCollapsedControl"] button,
    [data-testid="collapsedControl"] button {
      width:42px !important;
      height:42px !important;
      min-width:42px !important;
      min-height:42px !important;
      border:1px solid var(--os-border-strong) !important;
      border-radius:999px !important;
      background:var(--os-surface) !important;
      color:var(--os-text) !important;
      box-shadow:0 8px 24px rgba(15,23,42,.10) !important;
    }

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {
      direction:rtl !important;
      text-align:right !important;
      background:var(--os-surface) !important;
      border-left:1px solid var(--os-border) !important;
      border-right:0 !important;
      box-shadow:-8px 0 28px rgba(15,23,42,.035) !important;
    }
    section[data-testid="stSidebar"] > div {
      padding:1rem .8rem 1.5rem !important;
      direction:rtl !important;
    }
    section[data-testid="stSidebar"][aria-expanded="false"] {
      overflow:hidden !important;
      border:0 !important;
      box-shadow:none !important;
    }
    [data-testid="stSidebarResizer"] { display:none !important; }

    [data-testid="stSidebar"] [role="radiogroup"] { gap:.22rem !important; }
    [data-testid="stSidebar"] [role="radiogroup"] label {
      direction:rtl !important;
      width:100% !important;
      min-height:43px !important;
      padding:.52rem .7rem !important;
      border:1px solid transparent !important;
      border-radius:var(--os-radius-sm) !important;
      justify-content:flex-start !important;
      transition:background .16s ease,border-color .16s ease,transform .16s ease;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
      background:var(--os-hover) !important;
      border-color:rgba(36,87,230,.12) !important;
      transform:translateX(-2px);
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
      background:linear-gradient(135deg,rgba(36,87,230,.14),rgba(14,143,202,.07)) !important;
      border-color:rgba(36,87,230,.20) !important;
      color:var(--os-primary) !important;
      font-weight:800 !important;
    }

    /* ---------- Columns and responsive flow ---------- */
    [data-testid="stHorizontalBlock"], [data-testid="stColumns"] {
      direction:rtl !important;
      flex-direction:row !important;
      gap:.78rem !important;
      align-items:stretch !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"],
    [data-testid="stColumns"] > [data-testid="column"] {
      direction:rtl !important;
      text-align:right !important;
      min-width:0 !important;
    }

    /* ---------- Header ---------- */
    .os-app-header {
      width:100% !important;
      min-height:78px !important;
      max-height:112px !important;
      display:flex !important;
      align-items:center !important;
      justify-content:space-between !important;
      gap:1rem !important;
      direction:rtl !important;
      overflow:hidden !important;
      padding:.85rem 1rem !important;
      margin:0 0 .85rem !important;
      border:1px solid var(--os-border-strong) !important;
      border-radius:var(--os-radius-lg) !important;
      background:linear-gradient(135deg,rgba(36,87,230,.095),rgba(14,143,202,.045)),var(--os-surface) !important;
      box-shadow:var(--os-shadow) !important;
    }
    .os-h-left { display:flex !important; align-items:center !important; gap:.78rem !important; min-width:0 !important; direction:rtl !important; }
    .os-h-logo {
      width:56px !important; height:56px !important; min-width:56px !important; max-width:56px !important;
      overflow:hidden !important; border-radius:15px !important; background:#fff !important;
      border:1px solid var(--os-border) !important; display:grid !important; place-items:center !important;
    }
    .os-h-logo img { width:100% !important; height:100% !important; max-width:56px !important; max-height:56px !important; object-fit:contain !important; display:block !important; }
    .os-h-title { font-size:1.32rem !important; line-height:1.2 !important; font-weight:900 !important; color:var(--os-text) !important; white-space:nowrap !important; overflow:hidden !important; text-overflow:ellipsis !important; }
    .os-h-sub { margin-top:.2rem !important; font-size:.86rem !important; line-height:1.45 !important; font-weight:600 !important; color:var(--os-muted) !important; white-space:nowrap !important; overflow:hidden !important; text-overflow:ellipsis !important; }
    .os-h-right { display:flex !important; align-items:center !important; gap:.42rem !important; flex-wrap:wrap !important; justify-content:flex-end !important; }

    /* ---------- Login hero ---------- */
    .landing-hero {
      direction:rtl !important;
      padding:1.15rem 1.2rem !important;
      margin:.3rem 0 1rem !important;
      border:1px solid var(--os-border-strong) !important;
      border-radius:var(--os-radius-lg) !important;
      background:linear-gradient(135deg,rgba(36,87,230,.13),rgba(14,143,202,.06)),var(--os-surface) !important;
      box-shadow:var(--os-shadow) !important;
    }
    .landing-title { display:flex !important; align-items:center !important; gap:.65rem !important; font-size:1.6rem !important; font-weight:900 !important; }
    .landing-title img { width:44px !important; height:44px !important; object-fit:contain !important; }
    .landing-sub { margin-top:.35rem !important; color:var(--os-muted) !important; font-weight:600 !important; }

    /* ---------- Inputs ---------- */
    .stApp input:not([type="number"]), .stApp textarea,
    [data-baseweb="select"] input, [role="option"],
    [data-baseweb="popover"], [data-baseweb="menu"] {
      direction:rtl !important;
      text-align:right !important;
      unicode-bidi:plaintext !important;
    }
    .stApp input[type="number"], .stApp input[type="tel"] {
      direction:ltr !important;
      text-align:right !important;
      unicode-bidi:isolate !important;
    }
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div,
    [data-testid="stDateInput"] > div > div {
      min-height:45px !important;
      border:1px solid var(--os-border-strong) !important;
      border-radius:var(--os-radius-sm) !important;
      background:var(--os-surface) !important;
      color:var(--os-text) !important;
      box-shadow:none !important;
    }
    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within,
    [data-baseweb="select"] > div:focus-within {
      border-color:rgba(36,87,230,.55) !important;
      box-shadow:var(--os-focus) !important;
    }
    .stApp label { color:var(--os-text) !important; font-weight:700 !important; }

    /* ---------- Buttons ---------- */
    .stButton > button, .stFormSubmitButton > button,
    [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {
      min-height:43px !important;
      border-radius:var(--os-radius-sm) !important;
      padding:.52rem .9rem !important;
      font-weight:800 !important;
      direction:rtl !important;
      border-color:var(--os-border-strong) !important;
      transition:transform .15s ease,box-shadow .15s ease,filter .15s ease !important;
    }
    [data-testid="stBaseButton-primary"], .stFormSubmitButton > button[kind="primary"] {
      color:#fff !important;
      border-color:transparent !important;
      background:linear-gradient(135deg,var(--os-primary),var(--os-primary-2)) !important;
      box-shadow:0 8px 20px rgba(36,87,230,.20) !important;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover { transform:translateY(-1px) !important; filter:brightness(1.015) !important; }

    /* ---------- Forms, cards and metrics ---------- */
    [data-testid="stForm"], div[data-testid="stExpander"] details,
    .os-card, .kpi-card, .stat-card, .card {
      background:var(--os-surface) !important;
      border:1px solid var(--os-border) !important;
      border-radius:var(--os-radius-md) !important;
      box-shadow:0 6px 22px rgba(15,23,42,.045) !important;
    }
    [data-testid="stForm"] { padding:1rem !important; }

    [data-testid="stMetric"] {
      direction:rtl !important;
      text-align:right !important;
      min-height:105px !important;
      padding:.85rem .95rem !important;
      border:1px solid var(--os-border) !important;
      border-radius:var(--os-radius-md) !important;
      background:var(--os-surface) !important;
      box-shadow:0 5px 18px rgba(15,23,42,.04) !important;
    }
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
      width:100% !important;
      justify-content:flex-start !important;
      text-align:right !important;
    }
    [data-testid="stMetricLabel"] { color:var(--os-muted) !important; font-weight:700 !important; }
    [data-testid="stMetricValue"] { color:var(--os-text) !important; font-weight:900 !important; direction:ltr !important; unicode-bidi:isolate !important; text-align:right !important; }
    [data-testid="stMetricDelta"] { direction:ltr !important; unicode-bidi:isolate !important; }

    .kpi-card {
      position:relative !important;
      min-height:116px !important;
      height:100% !important;
      padding:.9rem 1rem !important;
      overflow:hidden !important;
      transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease !important;
    }
    .kpi-card:hover, .os-card:hover { transform:translateY(-2px); border-color:rgba(36,87,230,.20) !important; box-shadow:var(--os-shadow) !important; }
    .kpi-icon-bg { font-size:1.15rem !important; line-height:1 !important; margin-bottom:.45rem !important; }
    .kpi-label { color:var(--os-muted) !important; font-size:.82rem !important; font-weight:700 !important; }
    .kpi-value { margin-top:.2rem !important; color:var(--os-text) !important; font-size:1.45rem !important; font-weight:900 !important; line-height:1.3 !important; overflow-wrap:anywhere !important; }

    .tasi-card {
      min-height:118px !important;
      height:100% !important;
      display:flex !important;
      align-items:center !important;
      justify-content:space-between !important;
      gap:1rem !important;
      padding:1rem 1.15rem !important;
      border-radius:var(--os-radius-md) !important;
      color:#fff !important;
      background:linear-gradient(135deg,#173c99,#087baa) !important;
      box-shadow:0 12px 28px rgba(23,60,153,.20) !important;
    }

    .os-card { padding:1rem !important; margin:.45rem 0 !important; color:var(--os-text) !important; }
    .os-card-title { display:flex !important; align-items:center !important; gap:.42rem !important; margin-bottom:.7rem !important; color:var(--os-text) !important; font-size:1.02rem !important; font-weight:850 !important; }
    .os-kv { display:flex !important; align-items:flex-start !important; justify-content:space-between !important; gap:1rem !important; padding:.5rem 0 !important; border-bottom:1px dashed var(--os-border) !important; }
    .os-kv:last-child { border-bottom:0 !important; }
    .os-k { color:var(--os-muted) !important; font-weight:650 !important; }
    .os-v { color:var(--os-text) !important; font-weight:800 !important; text-align:left !important; overflow-wrap:anywhere !important; }

    .os-grid { display:grid !important; grid-template-columns:repeat(12,minmax(0,1fr)) !important; gap:.8rem !important; width:100% !important; }
    .os-col-3 { grid-column:span 3 !important; }
    .os-col-4 { grid-column:span 4 !important; }
    .os-col-6 { grid-column:span 6 !important; }
    .os-col-12 { grid-column:span 12 !important; }

    .os-chip {
      display:inline-flex !important; align-items:center !important; gap:.28rem !important;
      min-height:30px !important; padding:.25rem .62rem !important; margin:.1rem !important;
      border:1px solid transparent !important; border-radius:999px !important;
      font-size:.79rem !important; font-weight:800 !important; white-space:nowrap !important;
    }
    .os-chip-blue { color:#1d4ed8 !important; background:rgba(37,99,235,.10) !important; border-color:rgba(37,99,235,.16) !important; }
    .os-chip-green { color:#047857 !important; background:rgba(5,150,105,.10) !important; border-color:rgba(5,150,105,.17) !important; }
    .os-chip-red { color:#b91c1c !important; background:rgba(220,38,38,.09) !important; border-color:rgba(220,38,38,.16) !important; }
    .os-chip-amber { color:#b45309 !important; background:rgba(217,119,6,.10) !important; border-color:rgba(217,119,6,.18) !important; }
    .os-chip-gray { color:var(--os-muted) !important; background:var(--os-surface-soft) !important; border-color:var(--os-border) !important; }

    /* Legacy custom material words must never leak into the UI. */
    .os-card .mi, .os-chip .mi, .os-app-header .mi {
      display:inline-flex !important; width:.8rem !important; overflow:hidden !important;
      font-size:0 !important; line-height:1 !important; vertical-align:middle !important;
    }
    .os-card .mi::before, .os-chip .mi::before, .os-app-header .mi::before {
      content:'◆'; font-size:.55rem !important; color:currentColor !important;
    }

    /* ---------- Tabs, horizontal radios, expanders ---------- */
    [data-testid="stTabs"] { direction:rtl !important; }
    [data-testid="stTabs"] [role="tablist"] {
      direction:rtl !important;
      flex-direction:row !important;
      justify-content:flex-start !important;
      gap:.35rem !important;
      overflow-x:auto !important;
      padding:.25rem 0 .5rem !important;
    }
    [data-testid="stTabs"] [role="tab"] {
      direction:rtl !important;
      min-height:40px !important;
      padding:.48rem .8rem !important;
      border-radius:var(--os-radius-sm) !important;
      font-weight:750 !important;
      white-space:nowrap !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
      color:var(--os-primary) !important;
      background:rgba(36,87,230,.105) !important;
      box-shadow:inset 0 0 0 1px rgba(36,87,230,.14) !important;
    }

    [data-testid="stRadio"] [role="radiogroup"] {
      direction:rtl !important;
      justify-content:flex-start !important;
      gap:.35rem !important;
      flex-wrap:wrap !important;
    }
    [data-testid="stRadio"] [role="radiogroup"] label {
      direction:rtl !important;
      text-align:right !important;
    }

    div[data-testid="stExpander"] details { overflow:hidden !important; }
    div[data-testid="stExpander"] details summary {
      direction:rtl !important;
      text-align:right !important;
      min-height:47px !important;
      padding:.68rem .9rem !important;
      color:var(--os-text) !important;
      font-weight:800 !important;
    }

    /* ---------- Alerts ---------- */
    [data-testid="stAlert"] {
      direction:rtl !important;
      text-align:right !important;
      border-radius:var(--os-radius-sm) !important;
      border-width:1px !important;
      box-shadow:0 4px 16px rgba(15,23,42,.035) !important;
    }
    [data-testid="stAlert"] > div { direction:rtl !important; text-align:right !important; }

    /* ---------- Tables ---------- */
    .finance-table, .os-table, .stApp table {
      direction:rtl !important;
      width:100% !important;
      border-collapse:separate !important;
      border-spacing:0 !important;
      overflow:hidden !important;
      color:var(--os-text) !important;
      background:var(--os-surface) !important;
      border:1px solid var(--os-border) !important;
      border-radius:var(--os-radius-sm) !important;
    }
    .finance-table th, .os-table th, .stApp table th {
      text-align:right !important;
      color:var(--os-text) !important;
      background:rgba(36,87,230,.075) !important;
      font-weight:800 !important;
    }
    .finance-table td, .finance-table th,
    .os-table td, .os-table th, .stApp table td, .stApp table th {
      padding:.65rem .72rem !important;
      border-bottom:1px solid var(--os-border) !important;
      vertical-align:middle !important;
    }
    .finance-table tbody tr:nth-child(even), .os-table tbody tr:nth-child(even) { background:var(--os-row-alt) !important; }
    .finance-table tbody tr:hover, .os-table tbody tr:hover { background:var(--os-hover) !important; }
    .td-num, .num, .ticker-symbol, .finance-table td.td-num {
      direction:ltr !important;
      text-align:left !important;
      unicode-bidi:isolate !important;
      font-variant-numeric:tabular-nums;
    }
    .txt-green { color:var(--os-success) !important; }
    .txt-red { color:var(--os-danger) !important; }
    .txt-blue { color:var(--os-info) !important; }

    [data-testid="stDataFrame"], [data-testid="stTable"] {
      direction:rtl !important;
      overflow:hidden !important;
      border:1px solid var(--os-border) !important;
      border-radius:var(--os-radius-sm) !important;
      background:var(--os-surface) !important;
    }

    /* ---------- Plotly/media ---------- */
    [data-testid="stPlotlyChart"], [data-testid="stImage"], iframe {
      width:100% !important;
      max-width:100% !important;
      overflow:hidden !important;
      border-radius:var(--os-radius-sm) !important;
    }
    [data-testid="stPlotlyChart"] { direction:ltr !important; }
    .js-plotly-plot, .plot-container, .svg-container { max-width:100% !important; }
    img { max-width:100%; }

    @media (max-width:900px) {
      .block-container { padding:.8rem .65rem 2rem !important; }
      [data-testid="stHorizontalBlock"], [data-testid="stColumns"] {
        flex-direction:column !important;
        direction:rtl !important;
        gap:.55rem !important;
      }
      [data-testid="stHorizontalBlock"] > [data-testid="column"],
      [data-testid="stColumns"] > [data-testid="column"] {
        width:100% !important; flex:1 1 100% !important;
      }
      .os-app-header { min-height:70px !important; max-height:96px !important; padding:.7rem .75rem !important; }
      .os-h-logo { width:48px !important; height:48px !important; min-width:48px !important; max-width:48px !important; }
      .os-h-logo img { max-width:48px !important; max-height:48px !important; }
      .os-h-right { display:none !important; }
      .os-h-title { font-size:1.16rem !important; }
      .os-h-sub { font-size:.78rem !important; }
      .os-col-3, .os-col-4, .os-col-6 { grid-column:span 12 !important; }
      .kpi-card { min-height:100px !important; }
    }

    @media (max-width:560px) {
      .os-app-header { border-radius:15px !important; }
      .os-h-sub { white-space:normal !important; max-height:2.4em !important; }
      .landing-title { font-size:1.3rem !important; }
      [data-testid="stMetric"] { min-height:92px !important; }
      .kpi-value { font-size:1.25rem !important; }
    }
    </style>
    """
    return textwrap.dedent(css.replace("__PALETTE__", textwrap.dedent(palette).strip())).strip()


def apply_custom_css() -> None:
    """Inject the canonical stylesheet exactly once per Streamlit rerun."""
    st.markdown(build_app_css(_theme_name()), unsafe_allow_html=True)


def apply_ui_css() -> None:
    """Compatibility alias retained for older imports.

    It intentionally does nothing because :func:`apply_custom_css` already
    contains the complete visual system. Calling both used to duplicate CSS.
    """
    return None
