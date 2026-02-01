# ui/pages/analysis/thesis_tab.py
import streamlit as st

from ui.common import sym_key as _sym_key

try:
    from financial_analysis import get_thesis, save_thesis
except Exception:
    def get_thesis(s): return None
    def save_thesis(s, t, tg, r): pass


def render_thesis_tab(symbol: str):
    th = get_thesis(symbol)
    txt = th["thesis_text"] if (isinstance(th, dict) and "thesis_text" in th) else (
        th.thesis_text if th is not None and hasattr(th, "thesis_text") else ""
    )

    with st.form(f"th_{_sym_key(symbol)}"):
        nt = st.text_area("نص الأطروحة", value=txt)
        if st.form_submit_button("حفظ"):
            save_thesis(symbol, nt, 0, "Hold")
            st.success("تم")
