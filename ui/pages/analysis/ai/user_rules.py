# ui/pages/analysis/ai/user_rules.py
import streamlit as st


def render_user_rules_panel(
    symbol: str,
    save_user_rule_fn,
    load_user_rules_fn,
    on_saved=None,
):
    """
    Renders:
    - input textarea for user strategy/rules
    - save button
    - expander to show last saved rules
    """
    symk = (symbol or "sym").replace(".", "_").replace(" ", "_")

    st.subheader("🧠 استراتيجياتي الخاصة")
    st.caption("اكتب قواعدك بصيغة بسيطة مثل: (تقاطع الماكد صعوداً + اختراق خط الصفر) أو (RSI فوق 70)")

    rule_text = st.text_area("✍️ أدخل الاستراتيجية", key=f"user_rule_text_{symk}", height=110)
    col1, _ = st.columns([1, 2])

    with col1:
        if st.button("💾 حفظ الاستراتيجية", key=f"save_rule_{symk}", type="primary"):
            res = save_user_rule_fn(rule_text, title="قاعدة من المستخدم", enabled=1) if save_user_rule_fn else {"ok": False, "reason": "save_user_rule غير متوفر"}
            if isinstance(res, dict) and res.get("ok"):
                st.success("✅ تم حفظ الاستراتيجية")
                if callable(on_saved):
                    on_saved()
                st.rerun()
            else:
                st.error(f"لم يتم الحفظ: {res.get('reason','') if isinstance(res, dict) else 'Unknown'}")
                if isinstance(res, dict) and res.get("trace"):
                    with st.expander("Trace"):
                        st.code(res.get("trace"), language="text")

    with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
        rules = load_user_rules_fn(enabled_only=True, max_rows=10) if load_user_rules_fn else []
        rules = rules or []
        if rules:
            for r in rules:
                title = (r or {}).get("title", "قاعدة")
                txt = (r or {}).get("rule_text", "")
                st.write(f"- **{title}**: {txt}")
        else:
            st.info("لا توجد قواعد محفوظة بعد.")
