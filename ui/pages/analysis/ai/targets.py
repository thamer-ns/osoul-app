# ui/pages/analysis/ai/targets.py
import streamlit as st
import pandas as pd
from ui.pages.analysis.shared import safe_list, fmt_price


def render_targets(targets):
    targets = safe_list(targets)
    if not targets:
        st.info("لا توجد أهداف جاهزة حالياً.")
        return

    rows = []
    for t in targets[:8]:
        if isinstance(t, dict):
            rows.append({
                "الهدف": t.get("name") or t.get("label") or "Target",
                "السعر": fmt_price(t.get("price") or t.get("value")),
                "ملاحظة": t.get("note") or ""
            })
        else:
            rows.append({"الهدف": "Target", "السعر": fmt_price(t), "ملاحظة": ""})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
