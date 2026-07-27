"""Operational tools for evaluating and learning from completed signals."""
from __future__ import annotations

import streamlit as st

from tenant_scope import current_tenant


def _result_message(result) -> tuple[bool, str]:
    if isinstance(result, dict):
        ok = bool(result.get("ok", True))
        if ok:
            details = []
            if result.get("evaluated") is not None:
                details.append(f"تم تقييم {int(result['evaluated'])} إشارة")
            if result.get("updated") is not None:
                details.append(f"تم تحديث {int(result['updated'])} وزن")
            return True, " — ".join(details) or "اكتملت العملية"
        return False, str(result.get("reason") or "تعذر تنفيذ العملية")
    return True, "اكتملت العملية"


def _render_outcome_evaluation() -> None:
    with st.expander("📋 تقييم نتائج الإشارات", expanded=True):
        st.write(
            "يقارن النظام الإشارات السابقة بحركة السعر اللاحقة، ويحدد هل وصل "
            "السعر إلى الهدف أو وقف الخسارة أولًا. هذه الخطوة تقيس جودة المستشار "
            "ولا تغيّر أوزانه."
        )
        c1, c2, c3 = st.columns(3)
        interval = c1.selectbox(
            "فاصل التقييم",
            options=["1d", "1wk"],
            format_func=lambda value: "يومي" if value == "1d" else "أسبوعي",
            key="learning_eval_interval",
        )
        horizons = c2.multiselect(
            "آفاق التقييم",
            options=[4, 5, 8, 10, 13, 20, 26, 60],
            default=[5, 10, 20, 60],
            key="learning_eval_horizons",
        )
        max_rows = c3.number_input(
            "أقصى عدد إشارات",
            min_value=50,
            max_value=5000,
            value=400,
            step=50,
            key="learning_eval_rows",
        )
        if st.button(
            "تقييم الإشارات المستحقة",
            icon="📊",
            type="primary",
            use_container_width=True,
            key="learning_evaluate",
        ):
            try:
                from ai_engine_core.logging_learning import (
                    evaluate_pending_outcomes_pro,
                )

                result = evaluate_pending_outcomes_pro(
                    horizons=horizons or None,
                    max_rows=int(max_rows),
                    interval=str(interval),
                )
                ok, message = _result_message(result)
                st.success(message) if ok else st.error(message)
            except Exception:
                st.error("تعذر تقييم الإشارات. راجع سجل الخادم.")


def _render_weight_learning() -> None:
    with st.expander("🧠 تحديث أوزان المستشار", expanded=False):
        st.write(
            "بعد تكوّن عينة كافية من النتائج المقاسة، يمكن تعديل أوزان الأدلة "
            "داخل محفظتك فقط. لا يتم التحديث تلقائيًا ولا يؤثر في مستخدم آخر."
        )
        st.warning(
            "التحديث إحصائي ومتحفظ؛ لا تستخدم عينة صغيرة، ولا تعتبر النتيجة "
            "ضمانًا لأداء مستقبلي."
        )
        left, right = st.columns(2)
        target_horizon = left.selectbox(
            "أفق التعلم المستهدف",
            options=[4, 5, 8, 10, 13, 20, 26, 60],
            index=5,
            key="learning_target_horizon",
        )
        minimum_samples = right.number_input(
            "الحد الأدنى للعينات",
            min_value=20,
            max_value=500,
            value=50,
            step=5,
            key="learning_minimum_samples",
        )
        confirmed = st.checkbox(
            "أفهم أن العملية ستغيّر أوزان مستشار محفظتي",
            value=False,
            key="learning_confirm_update",
        )
        if st.button(
            "تحديث الأوزان من النتائج",
            icon="⚙️",
            disabled=not confirmed,
            use_container_width=True,
            key="learning_update_weights",
        ):
            try:
                from ai_engine_core.logging_learning import learn_from_history_pro

                result = learn_from_history_pro(
                    target_horizon=int(target_horizon),
                    min_samples=int(minimum_samples),
                )
                ok, message = _result_message(result)
                st.success(message) if ok else st.error(message)
            except Exception:
                st.error("تعذر تحديث الأوزان. راجع سجل الخادم.")


def view_tools() -> None:
    st.header("🛠️ أدوات التقييم والتعلم")
    tenant = current_tenant()
    if tenant is None:
        st.error("تعذر تحديد المحفظة النشطة")
        return

    st.caption(
        "يسجل المستشار إشارات التحليل تلقائيًا. هذه الصفحة تقيس نتائجها، ثم "
        "تتيح تحديث الأوزان يدويًا بعد توفر عينة كافية وبموافقتك."
    )
    _render_outcome_evaluation()
    _render_weight_learning()
