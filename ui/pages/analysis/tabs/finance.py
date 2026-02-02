# ui/pages/analysis/tabs/finance.py
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
    st.subheader("💰 التحليل المالي")

    # 1) حاول صفحة مالية قديمة عندك: ui/pages/analysis/financial_tab.py
    try:
        from ui.pages.analysis import financial_tab as legacy_fin
        ok = _call_first_available(
            legacy_fin,
            ["render", "render_finance", "render_financial", "render_financial_tab",
             "view", "view_finance", "view_financial"],
            fin, sym, symk
        )
        if ok:
            return

        # لو الملف القديم يوفر دالة مباشرة للوحة المالية
        fn = getattr(legacy_fin, "render_financial_dashboard_ui", None)
        if callable(fn):
            fn(sym)
            return
    except Exception:
        pass

    # 2) fallback من views_impl (لو لسه موجود)
    try:
        import views_impl as v
        fn = getattr(v, "render_financial_dashboard_ui", None)
        if callable(fn):
            fn(sym)
            return
    except Exception:
        pass

    st.warning("ما لقيت مشغل تبويب المالي. تأكد من وجود render_financial_dashboard_ui أو render(...) داخل financial_tab.py.")
    with st.expander("تفاصيل التشخيص"):
        st.code("Expected: ui/pages/analysis/financial_tab.py with render_financial_dashboard_ui(sym) or render(fin,sym,symk)", language="text")
