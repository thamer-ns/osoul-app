from __future__ import annotations

import streamlit as st

from views.shared import _sym_key, get_thesis, save_thesis


def _value(record, key, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    if record is not None and hasattr(record, key):
        return getattr(record, key)
    try:
        return record.get(key, default)
    except Exception:
        return default


def render_thesis_tab(symbol: str):
    record = get_thesis(symbol)
    existing_text = str(_value(record, "thesis_text", "") or "")
    existing_target = float(_value(record, "target_price", 0.0) or 0.0)
    existing_recommendation = str(
        _value(record, "recommendation", "Hold") or "Hold"
    )
    options = ["Buy", "Hold", "Reduce", "Sell"]
    if existing_recommendation not in options:
        existing_recommendation = "Hold"

    st.subheader("📝 أطروحة الاستثمار وخطة المتابعة")
    st.caption(
        "اكتب سبب امتلاك السهم، محفزات الصعود، المخاطر، وما الذي يُبطل الفرضية."
    )
    with st.form(f"thesis_{_sym_key(symbol)}"):
        text = st.text_area(
            "الأطروحة",
            value=existing_text,
            height=260,
            max_chars=20_000,
            placeholder=(
                "الفرضية الأساسية:\n"
                "المحفزات:\n"
                "المخاطر:\n"
                "شرط إبطال الفرضية:\n"
                "خطة المتابعة:"
            ),
        )
        left, right = st.columns(2)
        target = left.number_input(
            "السعر المستهدف",
            min_value=0.0,
            value=max(0.0, existing_target),
            step=0.01,
        )
        recommendation = right.selectbox(
            "الموقف الحالي",
            options,
            index=options.index(existing_recommendation),
        )
        submitted = st.form_submit_button(
            "حفظ الأطروحة",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not text.strip():
            st.warning("الأطروحة فارغة؛ اكتب الفرضية أو سبب المتابعة.")
        elif save_thesis(symbol, text, target, recommendation):
            st.success("تم حفظ الأطروحة")
            st.cache_data.clear()
        else:
            st.error("تعذر حفظ الأطروحة في قاعدة البيانات")
