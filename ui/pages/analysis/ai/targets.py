# ui/pages/analysis/ai/targets.py
import streamlit as st
import pandas as pd


def _to_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _fmt_price(x):
    v = _to_float(x, None)
    return "—" if v is None else f"{v:,.2f}"


def _safe_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [i for i in x if i is not None and str(i).strip() != ""]
    return [x]


def render_targets(targets):
    targets = _safe_list(targets)
    if not targets:
        st.info("لا توجد أهداف جاهزة حالياً.")
        return

    rows = []
    for t in targets[:8]:
        if isinstance(t, dict):
            rows.append({
                "الهدف": t.get("name") or t.get("label") or "Target",
                "السعر": _fmt_price(t.get("price") or t.get("value")),
                "ملاحظة": t.get("note") or ""
            })
        else:
            rows.append({"الهدف": "Target", "السعر": _fmt_price(t), "ملاحظة": ""})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
