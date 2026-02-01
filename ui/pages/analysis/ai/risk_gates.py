# ui/pages/analysis/ai/risk_gates.py
import streamlit as st
from ui.pages.analysis.shared import safe_list, badge


def render_risk_gates(risk_gates: dict):
    if not isinstance(risk_gates, dict) or not risk_gates:
        st.info("لا توجد بوابات مخاطر حالياً.")
        return

    passed = bool(risk_gates.get("pass", False))
    reasons = safe_list(risk_gates.get("reasons", []))

    c1, c2 = st.columns([1, 3])
    with c1:
        badge("✅ اجتاز" if passed else "❌ لم يجتز", "success" if passed else "danger")
    with c2:
        if reasons:
            st.markdown("**الأسباب:**")
            for r in reasons[:12]:
                st.write(f"- {r}")
        else:
            st.caption("لا توجد أسباب مسجلة.")
