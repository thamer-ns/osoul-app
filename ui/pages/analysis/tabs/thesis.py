# ui/pages/analysis/tabs/thesis.py
import streamlit as st
import traceback


def _call_first_available(mod, names, *args, **kwargs):
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            fn(*args, **kwargs)
            return True
    return False


def render(fin, sym: str, symk: str):
    st.subheader("📝 الأطروحة")

    # 1) حاول ui/pages/analysis/thesis_tab.py (قديم عندك غالباً)
    try:
        from ui.pages.analysis import thesis_tab as legacy_th
        ok = _call_first_available(
            legacy_th,
            ["render", "render_thesis", "render_thesis_tab", "view", "view_thesis", "tab"],
            fin, sym, symk
        )
        if ok:
            return
    except Exception:
        pass

    # 2) fallback: من financial_analysis (get_thesis/save_thesis)
    try:
        from financial_analysis import get_thesis, save_thesis
        th = get_thesis(sym)
        txt = th["thesis_text"] if (isinstance(th, dict) and "thesis_text" in th) else (
            th.thesis_text if th is not None and hasattr(th, "thesis_text") else ""
        )

        with st.form(f"th_{symk}"):
            nt = st.text_area("نص الأطروحة", value=txt, height=220)
            if st.form_submit_button("حفظ", type="primary"):
                save_thesis(sym, nt, 0, "Hold")
                st.success("تم الحفظ")
                st.rerun()
        return

    except Exception as e:
        st.error("تعذر تشغيل تبويب الأطروحة.")
        st.write(str(e))
        with st.expander("Trace"):
            st.code(traceback.format_exc(), language="text")
