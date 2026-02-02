# ui/pages/analysis/ai/user_rules.py
import streamlit as st


def render_user_rules_section(symbol: str, symk: str, save_user_rule_fn, load_user_rules_fn, clear_cache_fn):
    st.subheader("🧠 استراتيجياتي الخاصة")
    st.caption("اكتب قواعدك بصيغة بسيطة مثل: (تقاطع الماكد صعوداً + اختراق خط الصفر) أو (RSI فوق 70)")

    rule_text = st.text_area("✍️ أدخل الاستراتيجية", key=f"user_rule_text_{symk}", height=110)
    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("💾 حفظ الاستراتيجية", key=f"save_rule_{symk}", type="primary"):
            res = save_user_rule_fn(rule_text, title="قاعدة من المستخدم", enabled=1)
            if res.get("ok"):
                st.success("✅ تم حفظ الاستراتيجية")
                try:
                    clear_cache_fn(symbol)
                except Exception:
                    pass
                st.rerun()
            else:
                st.error(f"لم يتم الحفظ: {res.get('reason','')}")
                if res.get("trace"):
                    with st.expander("Trace"):
                        st.code(res.get("trace"), language="text")

    with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
        rules = load_user_rules_fn(enabled_only=True, max_rows=10) or []
        if rules:
            for r in rules:
                st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
        else:
            st.info("لا توجد قواعد محفوظة بعد.")
