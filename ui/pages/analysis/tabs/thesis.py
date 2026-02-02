# ui/pages/analysis/tabs/thesis.py
import streamlit as st
from datetime import date


def render(symbol: str):
    try:
        import views_impl as v

        symk = v._sym_key(symbol) if hasattr(v, "_sym_key") else (symbol or "sym").replace(".", "_")

        th = v.get_thesis(symbol) if hasattr(v, "get_thesis") else None
        txt = th["thesis_text"] if (isinstance(th, dict) and "thesis_text" in th) else (
            th.thesis_text if th is not None and hasattr(th, "thesis_text") else ""
        )

        with st.form(f"th_{symk}"):
            nt = st.text_area("نص الأطروحة", value=txt)
            if st.form_submit_button("حفظ"):
                if hasattr(v, "save_thesis"):
                    v.save_thesis(symbol, nt, 0, "Hold")
                    st.success("تم")
                else:
                    st.error("❌ save_thesis غير متوفر حالياً.")
    except Exception as e:
        st.error(f"❌ تعذر فتح تبويب الأطروحة: {e}")
