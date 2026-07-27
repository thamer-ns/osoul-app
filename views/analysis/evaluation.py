"""Evaluation and audit center for generated analysis outcomes."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
import streamlit as st

from ai_engine_core.evaluation_metrics import (
    build_evaluation_dataset,
    calibration_table,
    chronological_holdout,
    integrity_report,
    summary_metrics,
)
from components import render_custom_table, render_kpi
from database import fetch_table
from tenant_scope import current_tenant


def _frame(table: str) -> pd.DataFrame:
    try:
        value = fetch_table(table)
        return value if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
    except Exception:
        return pd.DataFrame()


def _fmt(value: Any, suffix: str = "", digits: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return f"{number:.{digits}f}{suffix}"


def _render_integrity(signals: pd.DataFrame, outcomes: pd.DataFrame) -> None:
    audit = integrity_report(signals, outcomes)
    with st.expander("🧾 سلامة السجل وقابلية التدقيق", expanded=not audit["pass"]):
        if audit["pass"]:
            st.success("لم تظهر مشكلات بنيوية في معرفات السجل أو JSON أو التواريخ.")
        else:
            st.error(" — ".join(str(item) for item in audit["issues"]))
        checks = pd.DataFrame(
            [
                {"الفحص": "إشارات مكررة", "العدد": audit["duplicate_signals"]},
                {"الفحص": "نتائج مكررة", "العدد": audit["duplicate_outcomes"]},
                {"الفحص": "نتائج يتيمة", "العدد": audit["orphan_outcomes"]},
                {"الفحص": "JSON غير صالح", "العدد": audit["invalid_json"]},
                {"الفحص": "عوائد غير رقمية", "العدد": audit["nonfinite_returns"]},
                {"الفحص": "تواريخ مستقبلية", "العدد": audit["future_dates"]},
            ]
        )
        render_custom_table(checks)


def _render_summary(dataset: pd.DataFrame) -> None:
    metrics = summary_metrics(dataset)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi("العينة المقاسة", str(metrics["samples"]), "neutral", "🧪")
    with c2:
        render_kpi("نسبة النجاح", _fmt(metrics["win_rate"], "%"), "blue", "✅")
    with c3:
        render_kpi("متوسط العائد", _fmt(metrics["average_return"], "%", 2), "neutral", "📈")
    with c4:
        render_kpi("Brier", _fmt(metrics["brier"], "", 3), "neutral", "🎯")
    with c5:
        render_kpi("ضرب الوقف", _fmt(metrics["sl_rate"], "%"), "danger", "🛡️")
    st.caption(
        "Brier يقيس دقة الاحتمال المعلن مقابل النتيجة الفعلية؛ الأصغر أفضل. "
        "لا تكفي نسبة النجاح وحدها، لأن العائد والمخاطرة والمعايرة وحجم العينة مهمة أيضًا."
    )


def _render_calibration(dataset: pd.DataFrame) -> None:
    probabilities = dataset.get("predicted_probability", pd.Series(dtype=float)).tolist()
    outcomes = pd.to_numeric(dataset.get("win_clean"), errors="coerce").fillna(-1).astype(int).tolist()
    table = calibration_table(probabilities, outcomes, bins=5)
    with st.expander("🎯 معايرة الثقة", expanded=True):
        if table.empty:
            st.info("لا توجد نتائج تحمل ثقة قابلة للمقارنة بعد.")
            return
        renamed = table.rename(
            columns={
                "bucket": "نطاق الثقة",
                "samples": "العينة",
                "mean_confidence": "متوسط الثقة %",
                "observed_win_rate": "النجاح الفعلي %",
                "calibration_gap": "فجوة المعايرة %",
            }
        )
        render_custom_table(renamed)
        st.caption("الفجوة الموجبة تعني أن الثقة أعلى من النتائج الفعلية، والسالبة تعني أن المحرك متحفظ.")


def _render_breakdowns(dataset: pd.DataFrame) -> None:
    with st.expander("📊 تفصيل الأداء", expanded=False):
        dimension = st.selectbox(
            "التقسيم",
            ["timeframe", "strategy_name", "direction", "lifecycle", "schools"],
            format_func=lambda value: {
                "timeframe": "الفاصل",
                "strategy_name": "الاستراتيجية",
                "direction": "الاتجاه",
                "lifecycle": "حالة الخطة",
                "schools": "توليفة المدارس",
            }[value],
            key="evaluation_dimension",
        )
        if dimension not in dataset.columns:
            st.info("هذا البعد غير متوفر في السجل الحالي.")
            return
        rows = []
        for value, group in dataset.groupby(dimension, dropna=False):
            metrics = summary_metrics(group)
            rows.append(
                {
                    "المجموعة": str(value or "غير مصنف"),
                    "العينة": metrics["samples"],
                    "النجاح %": metrics["win_rate"],
                    "متوسط العائد %": metrics["average_return"],
                    "وسيط العائد %": metrics["median_return"],
                    "Brier": metrics["brier"],
                    "TP %": metrics["tp_rate"],
                    "SL %": metrics["sl_rate"],
                }
            )
        if rows:
            render_custom_table(pd.DataFrame(rows).sort_values(["العينة", "النجاح %"], ascending=[False, False]))


def _render_chronological_holdout(dataset: pd.DataFrame) -> None:
    with st.expander("⏳ اختبار زمني خارج العينة", expanded=False):
        st.caption(
            "يُحفظ أقدم 75% كفترة سابقة، وتُقاس أحدث 25% كفترة لاحقة. "
            "لا نستخدم تقسيمًا عشوائيًا قد يخلط المستقبل بالماضي."
        )
        train, test = chronological_holdout(dataset, test_fraction=0.25)
        if test.empty or len(dataset) < 20:
            st.warning("تحتاج 20 نتيجة على الأقل ليصبح الاختبار الزمني ذا معنى أولي.")
            return
        past = summary_metrics(train)
        future = summary_metrics(test)
        table = pd.DataFrame(
            [
                {
                    "الفترة": "السابقة 75%",
                    "العينة": past["samples"],
                    "النجاح %": past["win_rate"],
                    "متوسط العائد %": past["average_return"],
                    "Brier": past["brier"],
                },
                {
                    "الفترة": "الأحدث 25%",
                    "العينة": future["samples"],
                    "النجاح %": future["win_rate"],
                    "متوسط العائد %": future["average_return"],
                    "Brier": future["brier"],
                },
            ]
        )
        render_custom_table(table)
        st.warning("هذا تدقيق وصفي زمني، وليس إثباتًا إحصائيًا للأداء المستقبلي.")


def _render_evaluation_action() -> None:
    with st.expander("🔄 تحديث النتائج المستحقة", expanded=False):
        st.write(
            "يقارن الإشارات القديمة بحركة السعر التالية ويحدد أول وصول للهدف أو الوقف. "
            "هذه العملية لا تغيّر الأوزان."
        )
        c1, c2, c3 = st.columns(3)
        interval = c1.selectbox("فاصل التقييم", ["1d", "1wk"], format_func=lambda value: "يومي" if value == "1d" else "أسبوعي", key="evaluation_interval")
        horizons = c2.multiselect("الآفاق", [4, 5, 8, 10, 13, 20, 26, 60], default=[5, 10, 20, 60], key="evaluation_horizons")
        max_rows = c3.number_input("أقصى إشارات", min_value=50, max_value=5000, value=400, step=50, key="evaluation_max_rows")
        if st.button("تقييم الإشارات المستحقة", type="primary", use_container_width=True, key="evaluation_run_pending"):
            try:
                from ai_engine_core.logging_learning import evaluate_pending_outcomes_pro

                result = evaluate_pending_outcomes_pro(horizons=horizons or None, max_rows=int(max_rows), interval=str(interval))
                if isinstance(result, dict) and not bool(result.get("ok", True)):
                    st.error(str(result.get("reason") or "تعذر التقييم"))
                else:
                    evaluated = (result or {}).get("evaluated") if isinstance(result, dict) else None
                    st.success("اكتمل التقييم" + (f" — {int(evaluated)} إشارة" if evaluated is not None else ""))
                    st.cache_data.clear()
                    st.rerun()
            except Exception:
                st.error("تعذر تقييم الإشارات. تم تسجيل التفاصيل لدى الخادم.")
        st.caption("تحديث أوزان المستشار يبقى يدويًا ومنفصلًا داخل صفحة الأدوات وبعد تأكيد صريح.")


def render_evaluation_center(finance: dict | None = None) -> None:
    st.header("🧪 التقييم والتدقيق")
    tenant = current_tenant()
    if tenant is None:
        st.error("تعذر تحديد المحفظة النشطة.")
        return
    st.caption(
        "قياس أداء الإشارات وجودة الاحتمالات وسلامة السجل للمحفظة النشطة. "
        "لا يتم تعديل الأوزان أو القواعد تلقائيًا من هذه الصفحة."
    )
    _render_evaluation_action()
    signals = _frame("ai_signals")
    outcomes = _frame("ai_outcomes")
    _render_integrity(signals, outcomes)
    dataset = build_evaluation_dataset(signals, outcomes)
    if dataset.empty:
        st.info("لا توجد نتائج مكتملة كافية بعد. ولّد تحليلات، ثم قيّم الإشارات المستحقة بعد مرور أفقها.")
        return
    _render_summary(dataset)
    _render_calibration(dataset)
    _render_breakdowns(dataset)
    _render_chronological_holdout(dataset)
