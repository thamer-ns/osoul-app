# ui/pages/analysis/ai/entry_risk.py
import streamlit as st
from ui.pages.analysis.shared import to_float, fmt_price


def render_entry_risk_levels(entry: dict, risk: dict, levels: dict, score: int):
    st.markdown("### 🧭 خطة الدخول والمخاطر")
    c1, c2, c3, c4 = st.columns(4)

    entry_zone = entry.get("entry_zone") or entry.get("zone") or entry.get("price")
    stop = risk.get("stop") or risk.get("sl") or risk.get("stop_loss")
    inv = risk.get("invalidation") or risk.get("invalid") or risk.get("break_level")
    rr = risk.get("rr") or risk.get("risk_reward")

    sup = levels.get("support")
    res = levels.get("resistance")

    with c1:
        st.metric("Score", f"{score}/100")
    with c2:
        st.metric("منطقة الدخول", fmt_price(entry_zone))
    with c3:
        st.metric("وقف الخسارة", fmt_price(stop))
    with c4:
        st.metric("إبطال الفكرة", fmt_price(inv))

    c5, c6, c7 = st.columns(3)
    with c5:
        st.metric("R:R", f"{to_float(rr, 0):.2f}" if rr is not None else "—")
    with c6:
        st.metric("Support", fmt_price(sup))
    with c7:
        st.metric("Resistance", fmt_price(res))
