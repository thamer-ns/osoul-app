#views/analysis/advisor.py
import streamlit as st
from views.shared import (
    _sym_key, _generate_ai_report_flex, _render_ai_report_readable,
    render_osoli_report, save_user_rule, load_user_rules
)

def render_advisor_tab(sym: str):
    symk = _sym_key(sym)
    tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}

    top1, top2, top3, top4 = st.columns([1.2, 1.8, 1.4, 1.0])
    ai_tf_label = top1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
    ai_tf = tf_map[ai_tf_label]

    view_mode = top2.radio(
        "طريقة العرض",
        ["مبسط", "تفصيلي", "بطاقات (Osoli)", "مطور (مع JSON)"],
        horizontal=True,
        key=f"ai_view_{symk}"
    )
    top3.caption("مبسط=مختصر | تفصيلي=كامل | بطاقات=واجهة أصولي | مطور=مع JSON")

    if top4.button("🔄 تحديث", key=f"ai_refresh_{symk}"):
        cache = st.session_state.get("_ai_rep_cache", {})
        for k in list(cache.keys()):
            if k.startswith(f"{sym}|"):
                del cache[k]
        st.session_state["_ai_rep_cache"] = cache
        st.rerun()

    cache = st.session_state.setdefault("_ai_rep_cache", {})
    cache_key = f"{sym}|{ai_tf}"

    if cache_key in cache:
        rep = cache[cache_key]
    else:
        with st.spinner("جاري توليد تقرير المستشار..."):
            rep = _generate_ai_report_flex(sym, timeframe=ai_tf)
        cache[cache_key] = rep

    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("فشل تشغيل المستشار (AI Engine).")
        st.code(rep.get("__trace__", ""))
        st.warning("سأكمل عرض بقية التبويبات (مالي/فني/كلاسيكي).")
    else:
        if view_mode == "مبسط":
            _render_ai_report_readable(rep, show_debug=False, compact=True)
        elif view_mode == "تفصيلي":
            _render_ai_report_readable(rep, show_debug=False, compact=False)
        elif view_mode == "بطاقات (Osoli)":
            try:
                render_osoli_report(rep, title=f"🤖 تقرير المستشار | {ai_tf_label}")
            except Exception:
                _render_ai_report_readable(rep, show_debug=False, compact=False)
        else:
            _render_ai_report_readable(rep, show_debug=True, compact=False)

    st.markdown("---")
    st.subheader("🧠 استراتيجياتي الخاصة")
    st.caption("اكتب قواعدك بصيغة بسيطة مثل: (تقاطع الماكد صعوداً + اختراق خط الصفر) أو (RSI فوق 70)")

    rule_text = st.text_area("✍️ أدخل الاستراتيجية", key=f"user_rule_text_{symk}", height=110)
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("💾 حفظ الاستراتيجية", key=f"save_rule_{symk}", type="primary"):
            res = save_user_rule(rule_text, title="قاعدة من المستخدم", enabled=1)
            if res.get("ok"):
                st.success("✅ تم حفظ الاستراتيجية")
                cache = st.session_state.get("_ai_rep_cache", {})
                for k in list(cache.keys()):
                    if k.startswith(f"{sym}|"):
                        del cache[k]
                st.session_state["_ai_rep_cache"] = cache
                st.rerun()
            else:
                st.error(f"لم يتم الحفظ: {res.get('reason','')}")

    with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
        rules = load_user_rules(enabled_only=True, max_rows=10) or []
        if rules:
            for r in rules:
                st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
        else:
            st.info("لا توجد قواعد محفوظة بعد.")
