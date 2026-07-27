"""Unified, explicit-run analysis workspace.

The page presents one decision contract first, then lets the user drill into
schools, geometry, evidence, multi-timeframe context and optional SC compass
evidence.  Nothing heavy runs merely because Streamlit rerendered the page.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from ai_engine_core.compass_contract import compare_compass_with_report, parse_compass_payload
from components import render_custom_table, render_kpi
from views.shared import _generate_ai_report_flex, _sym_key

TIMEFRAME_LABELS = {
    "1m": "1 دقيقة",
    "5m": "5 دقائق",
    "15m": "15 دقيقة",
    "30m": "30 دقيقة",
    "1h": "ساعة",
    "4h": "4 ساعات",
    "1d": "يومي",
    "1wk": "أسبوعي",
    "1mo": "شهري",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _tone(direction: str, status: str) -> str:
    if status == "BLOCKED":
        return "danger"
    if status == "HEADS_UP":
        return "warning"
    if status != "ACTIONABLE":
        return "neutral"
    return "success" if direction == "buy" else "danger"


def _report_cache() -> dict[str, Any]:
    cache = st.session_state.get("analysis_v4_cache")
    if not isinstance(cache, dict):
        cache = {}
        st.session_state["analysis_v4_cache"] = cache
    return cache


def _cache_key(symbol: str, timeframe: str) -> str:
    return f"{symbol}|{timeframe}"


def _generate(symbol: str, timeframe: str, *, refresh: bool = False) -> dict[str, Any]:
    cache = _report_cache()
    key = _cache_key(symbol, timeframe)
    if refresh:
        cache.pop(key, None)
    if key not in cache:
        report = _generate_ai_report_flex(symbol, timeframe=timeframe)
        cache[key] = {
            "report": report,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        st.session_state["analysis_v4_cache"] = cache
    value = cache.get(key) or {}
    return value if isinstance(value, dict) else {}


def _status_label(status: str) -> str:
    return {
        "ACTIONABLE": "قابلة للتنفيذ",
        "HEADS_UP": "قرب الدخول",
        "BLOCKED": "محظورة",
        "NO_SETUP": "مراقبة",
        "ERROR": "غير متاح",
    }.get(status, status or "غير متاح")


def _render_decision(report: dict[str, Any], generated_at: str) -> None:
    decision = report.get("decision_engine") if isinstance(report.get("decision_engine"), dict) else {}
    consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
    geometry = report.get("plan_geometry") if isinstance(report.get("plan_geometry"), dict) else {}
    contract = report.get("analysis_contract") if isinstance(report.get("analysis_contract"), dict) else {}
    direction = str(report.get("direction") or "neutral")
    status = str(report.get("lifecycle_status") or decision.get("status") or "NO_SETUP")
    confidence = _finite(report.get("confidence")) or 0.0
    direction_score = _finite(report.get("direction_score")) or 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi("المرحلة", str(report.get("analysis_stage") or _status_label(status)), _tone(direction, status), "🧭")
    with c2:
        render_kpi("الاتجاه", "صاعد" if direction == "buy" else "هابط" if direction == "sell" else "محايد", _tone(direction, status), "↕️")
    with c3:
        render_kpi("ثقة الأدلة", f"{confidence:.0f}%", "blue", "🎯")
    with c4:
        render_kpi("درجة الاتجاه", f"{direction_score:+.1f}", "neutral", "📐")
    with c5:
        render_kpi("المدارس المتوافقة", str(int(consensus.get("school_count") or 0)), "neutral", "🏫")

    recommendation = str(report.get("recommendation") or "لا توجد توصية")
    st.subheader(recommendation)
    st.caption(
        f"الحالة: {_status_label(status)} — تصنيف الفرصة: {report.get('opportunity_label', '—')} — "
        f"العقد: {contract.get('schema_version', '—')} — آخر توليد: {generated_at}"
    )
    if status != "ACTIONABLE":
        st.info("هذه النتيجة للمراقبة أو محظورة، ولا تُعامل كدخول حتى تصبح قابلة للتنفيذ وتنجح هندسة الخطة.")
    if not geometry.get("valid", False) and geometry.get("issues"):
        st.warning(" — ".join(str(item) for item in geometry.get("issues") or []))


def _render_schools(report: dict[str, Any]) -> None:
    consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
    with st.expander("🏫 توافق المدارس المستقلة", expanded=True):
        if not consensus:
            st.info("لا توجد نتيجة توافق منظمة.")
            return
        rule = "مدرسة واحدة قوية قابلة للتنفيذ" if consensus.get("strong_single_school") else "مدرستان مستقلتان أو أكثر"
        if consensus.get("qualified"):
            st.success(f"اجتاز شرط التوافق: {rule}")
        else:
            st.warning("لم يكتمل شرط التوافق أو ظهرت معارضة قوية.")
        rows = []
        for item in consensus.get("signals") or []:
            rows.append(
                {
                    "المدرسة": item.get("school"),
                    "المحور المستقل": item.get("axis"),
                    "الاتجاه": "صاعد" if item.get("direction") == 1 else "هابط",
                    "القوة": item.get("strength"),
                    "قابل للتنفيذ": bool(item.get("actionable")),
                    "السبب": item.get("reason"),
                }
            )
        if rows:
            render_custom_table(pd.DataFrame(rows))
        opposing = consensus.get("opposing") or []
        if opposing:
            st.markdown("**الأدلة المعارضة:**")
            for item in opposing:
                st.write(f"- {item.get('school')}: {item.get('reason')} ({item.get('strength')}/100)")


def _render_plan(report: dict[str, Any]) -> None:
    plan = report.get("risk_plan") if isinstance(report.get("risk_plan"), dict) else {}
    geometry = report.get("plan_geometry") if isinstance(report.get("plan_geometry"), dict) else {}
    with st.expander("🛡️ خطة الدخول والمخاطر", expanded=True):
        if plan.get("entry") is None:
            st.info("لا توجد خطة اتجاهية مكتملة لهذا الإغلاق.")
            return
        values = [
            ("الدخول", plan.get("entry")),
            ("الوقف", plan.get("stop")),
            ("الهدف 1", plan.get("target1")),
            ("الهدف 2", plan.get("target2")),
            ("الهدف 3", plan.get("target3")),
        ]
        columns = st.columns(5)
        for column, (label, value) in zip(columns, values):
            with column:
                st.metric(label, "—" if value is None else f"{float(value):,.4f}")
        r_values = geometry.get("target_r") or []
        st.caption(
            "العائد بوحدة R: "
            + " | ".join(f"T{index + 1}={value:.2f}R" for index, value in enumerate(r_values) if value is not None)
            + f" — الوقف: {geometry.get('stop_atr', '—')} ATR"
        )
        st.write(f"**الإبطال:** {plan.get('invalidation', '—')}")
        st.write(f"**انتهاء صلاحية المرشح:** بعد {plan.get('expiry_bars', '—')} شمعة دون تفعيل أو تقدم")
        st.caption("الكسر والوقف الفني يعتمدان إغلاق شمعة الفاصل. الأهداف تُتابع باللمس مع حفظ نتيجة الإغلاق للتدقيق.")


def _render_evidence(report: dict[str, Any]) -> None:
    evidence = list(report.get("top_evidence") or [])
    risks = list(report.get("top_risks") or [])
    left, right = st.columns(2)
    with left:
        with st.expander("✅ أقوى الأدلة", expanded=False):
            for item in evidence[:10]:
                st.write(f"- {item}")
            if not evidence:
                st.caption("لا توجد أدلة منظمة.")
    with right:
        with st.expander("⚠️ المخاطر والموانع", expanded=False):
            for item in risks[:10]:
                st.write(f"- {item}")
            if not risks:
                st.caption("لا توجد موانع مسجلة.")


def _render_lineage(report: dict[str, Any]) -> None:
    meta = report.get("engine_meta") if isinstance(report.get("engine_meta"), dict) else {}
    lineage = meta.get("data_lineage") if isinstance(meta.get("data_lineage"), dict) else {}
    with st.expander("🧾 مصدر البيانات وقابلية التدقيق", expanded=False):
        rows = {
            "المصدر": lineage.get("source") or "غير معروف",
            "وقت الجلب": lineage.get("fetched_at") or "—",
            "عدد الشموع المعتمدة": meta.get("rows") or 0,
            "آخر شمعة معتمدة": meta.get("last_bar") or "—",
            "شموع حية مستبعدة": meta.get("excluded_incomplete_bars") or 0,
            "إصدار محرك القرار": meta.get("decision_engine_version") or "—",
            "رقم الخطة": meta.get("plan_id") or "—",
        }
        render_custom_table(pd.DataFrame([{"البند": key, "القيمة": value} for key, value in rows.items()]))


def _render_multi_timeframe(symbol: str) -> None:
    with st.expander("🧩 مصفوفة الفواصل", expanded=False):
        st.caption("لا تعمل تلقائيًا. شغّلها عند الحاجة لأنها تولّد تقريرًا مستقلًا لكل فاصل.")
        selected = st.multiselect(
            "الفواصل المطلوبة",
            options=list(TIMEFRAME_LABELS),
            default=["15m", "1h", "4h", "1d", "1wk"],
            format_func=lambda item: TIMEFRAME_LABELS[item],
            key=f"mtf_frames:{_sym_key(symbol)}",
        )
        if st.button("تشغيل توافق الفواصل", type="primary", use_container_width=True, key=f"run_mtf:{_sym_key(symbol)}"):
            rows = []
            for timeframe in selected:
                with st.spinner(f"تحليل {TIMEFRAME_LABELS[timeframe]}..."):
                    payload = _generate(symbol, timeframe, refresh=True)
                report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
                consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
                rows.append(
                    {
                        "الفاصل": TIMEFRAME_LABELS[timeframe],
                        "المرحلة": report.get("analysis_stage") or "—",
                        "الاتجاه": "صاعد" if report.get("direction") == "buy" else "هابط" if report.get("direction") == "sell" else "محايد",
                        "الثقة": report.get("confidence"),
                        "المدارس": consensus.get("school_count", 0),
                        "قوة التوافق": consensus.get("strength", 0),
                        "هندسة الخطة": "صالحة" if (report.get("plan_geometry") or {}).get("valid") else "غير مكتملة",
                    }
                )
            st.session_state[f"mtf_result:{symbol}"] = rows
        rows = st.session_state.get(f"mtf_result:{symbol}") or []
        if rows:
            render_custom_table(pd.DataFrame(rows))


def _render_compass(symbol: str, report: dict[str, Any]) -> None:
    with st.expander("🧭 مقارنة تنبيه بوصلة TradingView", expanded=False):
        st.caption(
            "الصق JSON الذي يولده المؤشر من alert(). تتم مراجعته وعرض الاتفاق أو التعارض، "
            "ولا يغيّر قرار أصولي تلقائيًا. لا تضع أي Token أو رابط Webhook هنا."
        )
        text = st.text_area("JSON البوصلة", height=150, key=f"compass_json:{_sym_key(symbol)}")
        if st.button("تدقيق ومقارنة", use_container_width=True, key=f"compare_compass:{_sym_key(symbol)}"):
            try:
                parsed = parse_compass_payload(text)
                comparison = compare_compass_with_report(parsed, report)
                st.session_state[f"compass_result:{symbol}"] = {"parsed": parsed, "comparison": comparison}
            except ValueError as exc:
                st.error(str(exc))
        result = st.session_state.get(f"compass_result:{symbol}") or {}
        parsed = result.get("parsed") or {}
        comparison = result.get("comparison") or {}
        if parsed:
            if comparison.get("aligned"):
                st.success("البوصلة وأصولي متوافقان في الرمز والفاصل والاتجاه، مع بقاء القرار مستقلًا.")
            elif comparison.get("conflicts"):
                st.warning(" — ".join(str(item) for item in comparison.get("conflicts") or []))
            rows = {
                "المصدر": parsed.get("source"),
                "الحدث": parsed.get("event"),
                "الرمز": parsed.get("symbol"),
                "الفاصل": parsed.get("timeframe"),
                "الاتجاه": parsed.get("direction"),
                "التوافق": parsed.get("confidence"),
                "هندسة الخطة": "صالحة" if (parsed.get("geometry") or {}).get("valid") else "غير صالحة",
                "وقت الحدث": parsed.get("event_time"),
            }
            render_custom_table(pd.DataFrame([{"البند": key, "القيمة": value} for key, value in rows.items()]))
            with st.expander("البيانات المنظمة"):
                st.json(json.loads(json.dumps(parsed, ensure_ascii=False, default=str)))


def render_unified_overview(symbol: str, interval: str = "1d") -> None:
    st.subheader("🧭 النظرة الموحدة")
    st.caption(
        "قرار واحد يجمع المالي والفني والبنية والسلوك والمخاطر. لا يبدأ الحساب إلا عند الضغط، "
        "ولا تُستخدم الشمعة غير المكتملة في القرار."
    )
    left, right = st.columns([3, 1])
    run = left.button("تشغيل التحليل الموحد", type="primary", use_container_width=True, key=f"run_overview:{_sym_key(symbol)}:{interval}")
    refresh = right.button("إعادة الحساب", use_container_width=True, key=f"refresh_overview:{_sym_key(symbol)}:{interval}")
    if run or refresh:
        with st.spinner("جاري بناء القرار وتدقيق المدارس والخطة..."):
            _generate(symbol, interval, refresh=refresh)

    payload = _report_cache().get(_cache_key(symbol, interval)) or {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    if not report:
        st.info("اضغط «تشغيل التحليل الموحد» لبدء التحليل على الفاصل المختار.")
        _render_multi_timeframe(symbol)
        return
    if report.get("__error__") or str(report.get("status") or "").lower() == "error":
        st.error(str(report.get("message") or report.get("__error__") or "تعذر إكمال التحليل"))
        return

    _render_decision(report, str(payload.get("generated_at") or "—"))
    _render_schools(report)
    _render_plan(report)
    _render_evidence(report)
    _render_multi_timeframe(symbol)
    _render_compass(symbol, report)
    _render_lineage(report)
