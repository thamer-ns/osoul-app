#views/analysis/thesis.py
import streamlit as st
from views.shared import _sym_key, get_thesis, save_thesis

def render_thesis_tab(sym: str):
    th = get_thesis(sym)
    txt = th["thesis_text"] if (isinstance(th, dict) and "thesis_text" in th) else (
        th.thesis_text if th is not None and hasattr(th, "thesis_text") else ""
    )
    with st.form(f"th_{_sym_key(sym)}"):
        nt = st.text_area("نص الأطروحة", value=txt)
        if st.form_submit_button("حفظ"):
            save_thesis(sym, nt, 0, "Hold")
            st.success("تم")
