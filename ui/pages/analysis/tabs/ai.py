# ui/pages/analysis/tabs/ai.py
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
    """
    ✅ AI Tab entry point
    يحاول تشغيل تبويب AI من:
    - ui/pages/analysis/ai_tab.py   (قديم/مرحلة انتقالية)
    - ui/pages/analysis/ai/ai_tab.py (لو موجود)
    وإلا يعرض fallback بسيط.
    """
    st.subheader("🤖 المستشار (AI)")

    # 1) حاول تبويب AI القديم (غالباً عندك)
    try:
        from ui.pages.analysis import ai_tab as legacy_ai_tab
        ok = _call_first_available(
            legacy_ai_tab,
            ["render", "render_ai", "render_ai_tab", "view", "view_ai", "tab"],
            fin, sym, symk
        )
        if ok:
            return
    except Exception:
        pass

    # 2) حاول ai/ai_tab.py (لو موجود عندك)
    try:
        from ui.pages.analysis.ai import ai_tab as new_ai_tab
        ok = _call_first_available(
            new_ai_tab,
            ["render", "render_ai", "render_ai_tab", "view", "view_ai", "tab"],
            fin, sym, symk
        )
        if ok:
            return
    except Exception:
        pass

    # 3) fallback: شغّل عرض التقرير من views_impl لو متوفر
    try:
        import views_impl as v

        # حاول دوال عرض التقرير (إذا موجودة عندك في views_impl)
        # (نخليها مرنة لأنك ممكن غيرت أسماء)
        candidates_report = [
            "_generate_ai_report_flex",
            "generate_ai_report",
        ]
        gen = None
        for name in candidates_report:
            gen = getattr(v, name, None)
            if callable(gen):
                break

        render_readable = getattr(v, "_render_ai_report_readable", None)
        if callable(gen) and callable(render_readable):
            tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}
            c1, c2 = st.columns([1.2, 2.8])
            tf_label = c1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
            mode = c2.radio(
                "طريقة العرض",
                ["مبسط", "تفصيلي", "مطور (مع JSON)"],
                horizontal=True,
                key=f"ai_mode_{symk}"
            )

            with st.spinner("جاري توليد تقرير المستشار..."):
                rep = gen(sym, timeframe=tf_map[tf_label]) if "timeframe" in gen.__code__.co_varnames else gen(sym)

            if mode == "مبسط":
                render_readable(rep, show_debug=False, compact=True)
            elif mode == "تفصيلي":
                render_readable(rep, show_debug=False, compact=False)
            else:
                render_readable(rep, show_debug=True, compact=False)

            st.info("ℹ️ هذا fallback مؤقت — تبويب AI مقسّم عندك لكنه يحتاج entry point واضح.")
            return

    except Exception as e:
        st.error("تعذر تشغيل تبويب AI (fallback).")
        st.write(str(e))
        with st.expander("Trace"):
            st.code(traceback.format_exc(), language="text")
        return

    st.warning("تبويب AI موجود لكن ما لقيت دالة تشغيل في أي مكان. لازم يكون فيه render(...) أو view(...).")
