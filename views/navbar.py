#views/navbar.py
import streamlit as st


PAGES = [
    ("الرئيسية", "home"),
    ("التحليل", "analysis"),
    ("المحفظة", "portfolio"),
    ("الماسح", "screener"),
    ("الإعدادات", "settings"),
]


def get_current_page() -> str:
    qp = st.query_params
    page = qp.get("page", None)
    if isinstance(page, list):
        page = page[0] if page else None
    if not page:
        return "home"
    page = str(page).strip().lower()
    allowed = {p[1] for p in PAGES}
    return page if page in allowed else "home"


def set_page(page: str):
    st.query_params["page"] = page


def render_navbar():
    current = get_current_page()

    st.markdown(
        """
<div class="os-nav-wrap">
  <div class="os-nav-inner">
    <div class="os-brand">
      <div class="logo"></div>
      <div>
        <div class="title">أصولي</div>
        <div class="subtitle">لوحة التحليل والاستثمار</div>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # Chips row
    cols = st.columns([1, 8, 1])
    with cols[1]:
        chip_cols = st.columns(len(PAGES))
        for i, (label, key) in enumerate(PAGES):
            is_active = (key == current)
            btn_label = f"✅ {label}" if is_active else label
            if chip_cols[i].button(btn_label, use_container_width=True):
                set_page(key)
                st.rerun()

    # Small CSS enhancement: visually chip-like buttons
    st.markdown(
        """
<style>
/* Turn Streamlit buttons inside navbar into chips */
div[data-testid="column"] .stButton > button{
  border-radius: 999px !important;
  padding: 0.45rem 0.75rem !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  border: 1px solid rgba(255,255,255,.10) !important;
  background: rgba(255,255,255,.03) !important;
  color: rgba(255,255,255,.82) !important;
}

div[data-testid="column"] .stButton > button:hover{
  border-color: rgba(255,255,255,.16) !important;
  background: rgba(255,255,255,.05) !important;
}

div[data-testid="column"] .stButton > button:has(span:contains("✅")){
  border-color: rgba(79,70,229,.65) !important;
  background: rgba(79,70,229,.20) !important;
  color: rgba(255,255,255,.95) !important;
}
</style>
""",
        unsafe_allow_html=True,
    )
