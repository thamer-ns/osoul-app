# ui/pages/analysis/ai/controls.py
import streamlit as st

from ui.pages.analysis.shared import badge


def _k(symbol: str) -> str:
    s = (symbol or "sym").replace(".", "_").replace(" ", "_")
    return s


def render_ai_controls(symbol: str, ai_engine_ok: bool):
    """
    UI controls for AI tab:
    - timeframe
    - view mode
    - status badge
    - refresh button (returns bool)

    Returns:
      {
        "tf_label": str,
        "tf": str,
        "view_mode": str,
        "refresh": bool,
      }
    """
    symk = _k(symbol)

    tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}
    view_modes = ["مبسط", "تفصيلي", "بطاقات (Osoli)", "مطور (مع JSON)"]

    top1, top2, top3, top4 = st.columns([1.2, 1.8, 1.4, 1.0])
    ai_tf_label = top1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
    ai_tf = tf_map[ai_tf_label]

    view_mode = top2.radio(
        "طريقة العرض",
        view_modes,
        horizontal=True,
        key=f"ai_view_{symk}",
    )
    top3.caption("مبسط=مختصر | تفصيلي=كامل | بطاقات=واجهة أصولي | مطور=مع JSON")

    with top4:
        badge("AI: OK" if ai_engine_ok else "AI: Error", "success" if ai_engine_ok else "danger")

    refresh = st.button("🔄 تحديث المستشار", key=f"ai_refresh_{symk}")

    return {"tf_label": ai_tf_label, "tf": ai_tf, "view_mode": view_mode, "refresh": refresh}
