# ui/pages/analysis/ai/entry_risk.py
import streamlit as st


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


def render_entry_risk_levels(entry: dict, risk: dict, levels: dict, score: int):
    st.markdown("### 🧭 خطة الدخول والمخاطر")
    c1, c2, c3, c4 = st.columns(4)

    entry_zone = (entry or {}).get("entry_zone") or (entry or {}).get("zone") or (entry or {}).get("price")
    stop = (risk or {}).get("stop") or (risk or {}).get("sl") or (risk or {}).get("stop_loss")
    inv = (risk or {}).get("invalidation") or (risk or {}).get("invalid") or (risk or {}).get("break_level")
    rr = (risk or {}).get("rr") or (risk or {}).get("risk_reward")

    sup = (levels or {}).get("support")
    res = (levels or {}).get("resistance")

    with c1:
        st.metric("Score", f"{int(score)}/100")
    with c2:
        st.metric("منطقة الدخول", _fmt_price(entry_zone))
    with c3:
        st.metric("وقف الخسارة", _fmt_price(stop))
    with c4:
        st.metric("إبطال الفكرة", _fmt_price(inv))

    c5, c6, c7 = st.columns(3)
    with c5:
        st.metric("R:R", f"{_to_float(rr, 0):.2f}" if rr is not None else "—")
    with c6:
        st.metric("Support", _fmt_price(sup))
    with c7:
        st.metric("Resistance", _fmt_price(res))
