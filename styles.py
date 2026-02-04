# styles.py
import streamlit as st


def apply_global_styles():
    """
    Global UI / CSS for Osoli.

    Goals:
    - Centered content (max-width) even in wide layout
    - Reduce excessive whitespace
    - Modern navbar chips styles
    - Better readable "note" blocks instead of code-like boxes
    - RTL-friendly tweaks (without breaking existing RTL)
    """

    st.markdown(
        """
<style>
/* -------------------------
   Layout: wide but centered
-------------------------- */
:root{
  --os-bg: #0e1117;
  --os-panel: #111827;
  --os-panel-2:#0b1220;
  --os-border: rgba(255,255,255,.08);
  --os-border-2: rgba(255,255,255,.12);
  --os-text: rgba(255,255,255,.92);
  --os-muted: rgba(255,255,255,.72);
  --os-muted2: rgba(255,255,255,.56);
  --os-accent: #4f46e5;
  --os-accent2:#22c55e;
  --os-warn:#f59e0b;
  --os-danger:#ef4444;
  --os-radius: 16px;
  --os-shadow: 0 12px 30px rgba(0,0,0,.35);
  --os-shadow-soft: 0 8px 18px rgba(0,0,0,.25);
  --os-font: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Noto Kufi Arabic", "Noto Sans Arabic";
}

html, body, [class*="css"]{
  font-family: var(--os-font);
}

/* Streamlit main container centering */
section.main > div{
  max-width: 1280px;
  margin-left: auto;
  margin-right: auto;
  padding-left: 18px;
  padding-right: 18px;
}

/* Reduce vertical whitespace between blocks */
.block-container{
  padding-top: 1.5rem !important;
  padding-bottom: 2.0rem !important;
}

/* Hide Streamlit default menu/footer for cleaner app feel */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* -------------------------
   Navbar (chips)
-------------------------- */
.os-nav-wrap{
  position: sticky;
  top: 0;
  z-index: 999;
  backdrop-filter: blur(8px);
  background: linear-gradient(180deg, rgba(14,17,23,.92), rgba(14,17,23,.75));
  border-bottom: 1px solid var(--os-border);
  padding: 10px 0 12px 0;
  margin: -10px -18px 18px -18px; /* stretch edge-to-edge inside centered container */
}

.os-nav-inner{
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.os-brand{
  display:flex;
  align-items:center;
  gap:10px;
  min-width: max-content;
}

.os-brand .logo{
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: radial-gradient(circle at 25% 20%, rgba(79,70,229,.95), rgba(34,197,94,.85));
  box-shadow: var(--os-shadow-soft);
}

.os-brand .title{
  font-weight: 800;
  letter-spacing: .2px;
  color: var(--os-text);
  font-size: 16px;
  line-height: 1.1;
}

.os-brand .subtitle{
  font-size: 12px;
  color: var(--os-muted2);
  line-height: 1.1;
}

.os-chips{
  display:flex;
  align-items:center;
  gap: 8px;
  overflow-x: auto;
  padding: 4px 2px;
  scrollbar-width: thin;
}

.os-chip{
  border: 1px solid var(--os-border);
  background: rgba(255,255,255,.03);
  color: var(--os-muted);
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;
  cursor: pointer;
  transition: all .18s ease;
  user-select: none;
}

.os-chip:hover{
  transform: translateY(-1px);
  border-color: var(--os-border-2);
  color: var(--os-text);
  background: rgba(255,255,255,.05);
}

.os-chip.active{
  background: rgba(79,70,229,.22);
  border-color: rgba(79,70,229,.65);
  color: rgba(255,255,255,.95);
}

/* -------------------------
   Cards & panels
-------------------------- */
.os-card{
  border: 1px solid var(--os-border);
  background: rgba(255,255,255,.03);
  border-radius: var(--os-radius);
  padding: 16px 18px;
  box-shadow: var(--os-shadow-soft);
}

.os-card h3, .os-card h2, .os-card h1{
  margin: 0 0 10px 0;
}

.os-divider{
  height: 1px;
  background: var(--os-border);
  margin: 14px 0;
}

/* -------------------------
   Note block (replace code-y look)
-------------------------- */
.os-note{
  border: 1px solid var(--os-border);
  background: rgba(255,255,255,.035);
  border-radius: 14px;
  padding: 14px 16px;
  line-height: 1.7;
  color: var(--os-text);
}

.os-note .label{
  font-weight: 800;
  font-size: 12px;
  letter-spacing: .2px;
  color: var(--os-muted2);
  margin-bottom: 8px;
}

/* -------------------------
   Improve default expander look
-------------------------- */
div[data-testid="stExpander"]{
  border: 1px solid var(--os-border) !important;
  border-radius: var(--os-radius) !important;
  background: rgba(255,255,255,.02) !important;
  overflow: hidden;
}

div[data-testid="stExpander"] summary{
  padding: 10px 14px !important;
}

div[data-testid="stExpander"] summary:hover{
  background: rgba(255,255,255,.03) !important;
}

/* -------------------------
   Dataframes spacing
-------------------------- */
div[data-testid="stDataFrame"]{
  border-radius: var(--os-radius);
  overflow: hidden;
  border: 1px solid var(--os-border);
}

/* -------------------------
   Buttons (Streamlit)
-------------------------- */
.stButton > button{
  border-radius: 999px !important;
  border: 1px solid var(--os-border) !important;
  background: rgba(255,255,255,.03) !important;
  color: var(--os-text) !important;
  font-weight: 700 !important;
  padding: 0.55rem 0.9rem !important;
  transition: all .16s ease !important;
}

.stButton > button:hover{
  transform: translateY(-1px) !important;
  border-color: var(--os-border-2) !important;
  background: rgba(255,255,255,.05) !important;
}

/* Primary buttons: try to detect by aria-label may vary, keep subtle */
.stButton > button[kind="primary"]{
  border-color: rgba(79,70,229,.6) !important;
  background: rgba(79,70,229,.18) !important;
}

/* -------------------------
   RTL hints (keep existing RTL logic if present)
-------------------------- */
body{
  direction: rtl;
  text-align: right;
}

</style>
""",
        unsafe_allow_html=True,
    )
