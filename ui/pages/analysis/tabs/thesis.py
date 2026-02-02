# ui/pages/analysis/tabs/thesis.py
import streamlit as st
from ui.common import sym_key as _sym_key

from financial_analysis import get_thesis, save_thesis


def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    th = get_thesis(symbol)

    txt = ""
    if isinstance(th, dict) and "thesis_text" in th:
        txt = th.get("thesis_text") or ""
    elif th is not None and hasattr(th, "thesis_text"):
        txt = getattr(th, "thesis_text") or ""

    with st.form(f"th_{_sym_key(symbol)}"):
        st.caption("اكتب أطروحتك الاستثمارية لهذا السهم (لماذا تملكه؟ متى تبيع؟ ما المخاطر؟)")
        nt = st.text_area("نص الأطروحة", value=str(txt), height=220)
        if st.form_submit_button("حفظ", type="primary"):
            save_thesis(symbol, nt, 0, "Hold")
            st.success("تم الحفظ ✅")
