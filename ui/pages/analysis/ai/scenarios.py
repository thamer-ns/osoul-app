# ui/pages/analysis/ai/scenarios.py
import streamlit as st
from ui.pages.analysis.shared import safe_list, badge, to_float, fmt_price


def render_scenarios(scenarios):
    scenarios = safe_list(scenarios)
    if not scenarios:
        st.info("لا توجد سيناريوهات جاهزة حالياً.")
        return

    for i, sc in enumerate(scenarios[:8], start=1):
        if not isinstance(sc, dict):
            continue

        name = sc.get("name", f"سيناريو {i}")
        trigger = sc.get("trigger") or sc.get("condition") or "—"
        entry = sc.get("entry")
        stop = sc.get("stop") or sc.get("sl")
        t1 = sc.get("target1") or sc.get("target") or sc.get("tp1")
        t2 = sc.get("target2") or sc.get("tp2")
        t_list = sc.get("targets") if isinstance(sc.get("targets"), list) else None
        note = sc.get("note", "")

        st.markdown(
            """
            <div style="
                border:1px solid rgba(0,0,0,0.08);
                border-radius:14px;
                padding:14px;
                margin:10px 0;
                background:#fff;
            ">
            """,
            unsafe_allow_html=True
        )

        top = st.columns([2, 1])
        with top[0]:
            st.markdown(f"### {name}")
            st.caption(f"🎯 الشرط: {trigger}")
        with top[1]:
            e = to_float(entry, None)
            s = to_float(stop, None)
            tg = to_float(t1, None)
            if e is not None and s is not None and tg is not None and (e - s) != 0:
                rr = (tg - e) / (e - s)
                badge(f"R:R {rr:.2f}", "success" if rr >= 1.5 else "warning" if rr >= 1.0 else "danger")
            else:
                badge("سيناريو", "neutral")

        cA, cB, cC, cD = st.columns(4)
        cA.metric("الدخول", fmt_price(entry))
        cB.metric("وقف الخسارة", fmt_price(stop))
        cC.metric("الهدف 1", fmt_price(t1))
        cD.metric("الهدف 2", fmt_price(t2) if t2 is not None else "—")

        if t_list:
            st.caption("🎯 أهداف إضافية:")
            st.write([fmt_price(x.get("price") if isinstance(x, dict) else x) for x in t_list[:8]])

        if note:
            st.caption(f"📝 ملاحظة: {note}")

        st.markdown("</div>", unsafe_allow_html=True)
