# ui/pages/analysis/tabs/classical.py
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
    st.subheader("🏛️ التحليل الكلاسيكي")

    # 1) حاول ui/pages/analysis/classical_tab.py (قديم عندك غالباً)
    try:
        from ui.pages.analysis import classical_tab as legacy_classic
        ok = _call_first_available(
            legacy_classic,
            ["render", "render_classical", "render_classical_tab", "view", "view_classical", "tab"],
            fin, sym, symk
        )
        if ok:
            return
    except Exception:
        pass

    # 2) fallback: classical_analysis مباشرة
    try:
        from classical_analysis import render_classical_analysis
        render_classical_analysis(sym)
        return
    except Exception as e:
        st.error("تعذر تشغيل التحليل الكلاسيكي.")
        st.write(str(e))
        with st.expander("Trace"):
            st.code(traceback.format_exc(), language="text")
