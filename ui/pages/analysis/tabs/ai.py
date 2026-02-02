import streamlit as st


def render_tab(fin: dict, symbol: str):
    """
    تبويب المستشار (AI)
    - يعتمد على نفس دوال و Helpers الموجودة في views_impl.py (لضمان التطابق وعدم التكرار)
    - يقدّم نفس خيارات العرض + كاش + قواعد المستخدم + التشخيص
    """

    # استيراد مرن من views_impl لتفادي أي ImportError قاتل
    try:
        from views_impl import (
            _sym_key,
            AI_ENGINE_OK,
            _badge,
            _generate_ai_report_flex,
            _render_ai_report_readable,
            save_user_rule,
            load_user_rules,
            _ai_self_test,
            render_osoli_report,
        )
    except Exception as e:
        st.error("❌ تعذر تحميل تبويب AI بسبب مشكلة في views_impl.py")
        st.code(str(e))
        return

    symk = _sym_key(symbol)

    tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}

    top1, top2, top3, top4 = st.columns([1.2, 1.8, 1.4, 1.0])
    ai_tf_label = top1.selectbox(
        "الفاصل الزمني",
        list(tf_map.keys()),
        index=0,
        key=f"ai_tf_{symk}",
    )
    ai_tf = tf_map[ai_tf_label]

    view_mode = top2.radio(
        "طريقة العرض",
        ["مبسط", "تفصيلي", "بطاقات (Osoli)", "مطور (مع JSON)"],
        horizontal=True,
        key=f"ai_view_{symk}",
    )
    top3.caption("مبسط=مختصر | تفصيلي=كامل | بطاقات=واجهة أصولي | مطور=مع JSON")

    with top4:
        if AI_ENGINE_OK:
            _badge("AI: OK", "success")
        else:
            _badge("AI: Error", "danger")

    # زر تحديث: امسح كاش التقرير لهذا السهم
    if st.button("🔄 تحديث المستشار", key=f"ai_refresh_{symk}"):
        cache = st.session_state.get("_ai_rep_cache", {})
        for k in list(cache.keys()):
            if k.startswith(f"{symbol}|"):
                del cache[k]
        st.session_state["_ai_rep_cache"] = cache
        st.rerun()

    cache = st.session_state.setdefault("_ai_rep_cache", {})
    cache_key = f"{symbol}|{ai_tf}"

    if cache_key in cache:
        rep = cache[cache_key]
    else:
        with st.spinner("جاري توليد تقرير المستشار..."):
            rep = _generate_ai_report_flex(symbol, timeframe=ai_tf)

        # لا نخزن التقرير إذا فيه خطأ (عشان ما يثبت)
        if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
            pass
        else:
            cache[cache_key] = rep

    # عرض التقرير بحسب الوضع
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
            if isinstance(res, dict) and res.get("ok"):
                st.success("✅ تم حفظ الاستراتيجية")

                # امسح كاش هذا السهم لإعادة توليد التقرير
                cache = st.session_state.get("_ai_rep_cache", {})
                for k in list(cache.keys()):
                    if k.startswith(f"{symbol}|"):
                        del cache[k]
                st.session_state["_ai_rep_cache"] = cache
                st.rerun()
            else:
                reason = ""
                trace = ""
                if isinstance(res, dict):
                    reason = res.get("reason", "")
                    trace = res.get("trace", "")
                st.error(f"لم يتم الحفظ: {reason}")
                if trace:
                    with st.expander("Trace"):
                        st.code(trace, language="text")

    with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
        rules = load_user_rules(enabled_only=True, max_rows=10) or []
        if rules:
            for r in rules:
                st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
        else:
            st.info("لا توجد قواعد محفوظة بعد.")

    with st.expander("🧪 تشخيص المستشار (AI Engine Diagnostics)"):
        st.json(_ai_self_test())
        if not AI_ENGINE_OK:
            st.warning("المشكلة غالباً داخل ai_engine.py (ImportError/Dependency/NameError).")
