"""Structured advisor presentation for the v5 analysis contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi
from views.shared import _generate_ai_report_flex, _sym_key, load_user_rules, save_user_rule


def _cache() -> dict[str, Any]:
    value = st.session_state.get("advisor_v5_cache")
    if not isinstance(value, dict):
        value = {}
        st.session_state["advisor_v5_cache"] = value
    return value


def _run(symbol: str, timeframe: str, refresh: bool = False) -> dict[str, Any]:
    cache = _cache()
    key = f"{symbol}|{timeframe}"
    if refresh:
        cache.pop(key, None)
    if key not in cache:
        cache[key] = {
            "report": _generate_ai_report_flex(symbol, timeframe=timeframe),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    st.session_state["advisor_v5_cache"] = cache
    return cache[key]


def _render_summary(report: dict[str, Any], generated_at: str) -> None:
    consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
    reliability = report.get("data_reliability") if isinstance(report.get("data_reliability"), dict) else {}
    status = str(report.get("lifecycle_status") or "NO_SETUP")
    direction = str(report.get("direction") or "neutral")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi("رأي المستشار", str(report.get("analysis_stage") or "مراقبة"), "blue", "🤖")
    with c2:
        render_kpi("الاتجاه", "صاعد" if direction == "buy" else "هابط" if direction == "sell" else "محايد", "neutral", "↕️")
    with c3:
        render_kpi("الثقة", f"{float(report.get('confidence') or 0):.0f}%", "neutral", "🎯")
    with c4:
        render_kpi("المدارس", str(consensus.get("school_count") or 0), "neutral", "🏫")
    with c5:
        render_kpi("موثوقية البيانات", f"{int(reliability.get('score') or 0)}/100", "success" if reliability.get("pass") else "warning", "🧾")
    st.subheader(str(report.get("recommendation") or "لا توجد نتيجة"))
    st.write(str(report.get("strategy") or ""))
    contract = report.get("analysis_contract") if isinstance(report.get("analysis_contract"), dict) else {}
    st.caption(
        f"الحالة التنفيذية: {status} — القرار: {contract.get('decision_version', '—')} — "
        f"محرك النماذج: {contract.get('breakout_engine', '—')} — التوليد: {generated_at}"
    )


def _render_intelligence(report: dict[str, Any]) -> None:
    intelligence = report.get("advisor_intelligence") if isinstance(report.get("advisor_intelligence"), dict) else {}
    left, right = st.columns(2)
    with left:
        st.markdown("#### ماذا جمع المستشار؟")
        for item in intelligence.get("insights") or []:
            st.write(f"- {item}")
        if not intelligence.get("insights"):
            st.caption("لا توجد إضافات فوق القرار الأساسي.")
    with right:
        st.markdown("#### نقاط الحذر")
        for item in intelligence.get("cautions") or []:
            st.write(f"- {item}")
        if not intelligence.get("cautions"):
            st.caption("لم تظهر تعارضات إضافية.")


def _render_explanation(report: dict[str, Any]) -> None:
    consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
    left, right = st.columns(2)
    with left:
        st.markdown("#### لماذا ظهر هذا الرأي؟")
        for item in (report.get("top_evidence") or [])[:10]:
            st.write(f"- {item}")
    with right:
        st.markdown("#### ما الذي قد يفسده؟")
        for item in (report.get("top_risks") or [])[:10]:
            st.write(f"- {item}")
    with st.expander("تفاصيل المدارس المستقلة", expanded=False):
        rows = []
        for item in consensus.get("signals") or []:
            rows.append(
                {
                    "المدرسة": item.get("school"),
                    "المحور": item.get("axis"),
                    "القوة": item.get("strength"),
                    "تأكيد تنفيذي": bool(item.get("actionable")),
                    "السبب": item.get("reason"),
                }
            )
        if rows:
            render_custom_table(pd.DataFrame(rows))
        else:
            st.info("لم يكتمل توافق المدارس بعد.")


def _render_breakouts(report: dict[str, Any]) -> None:
    breakout = report.get("breakout_engine") if isinstance(report.get("breakout_engine"), dict) else {}
    with st.expander("📐 نماذج الاختراق SC-V90 داخل القرار", expanded=False):
        if not breakout.get("ok"):
            st.info("لا توجد بيانات كافية لمحرك النماذج أو لم يظهر نموذج صالح.")
            return
        st.write(str(breakout.get("summary") or ""))
        patterns = pd.DataFrame(breakout.get("patterns") or [])
        if patterns.empty:
            st.caption("لا يوجد نموذج واضح على آخر إغلاق.")
            return
        display = patterns.rename(
            columns={
                "name": "النموذج",
                "status": "الحالة",
                "direction": "الاتجاه",
                "confidence": "القوة",
                "boundary": "حد التنفيذ",
                "stop_reference": "مرجع الوقف",
                "measured_target": "الهدف المقاس",
                "reason": "السبب",
            }
        )
        display["الحالة"] = display["الحالة"].map({"CONFIRMED": "مؤكد", "FORMING": "تحت التكوين"})
        display["الاتجاه"] = display["الاتجاه"].map({1: "صاعد", -1: "هابط"})
        columns = [column for column in ["النموذج", "الحالة", "الاتجاه", "القوة", "حد التنفيذ", "مرجع الوقف", "الهدف المقاس", "السبب"] if column in display.columns]
        render_custom_table(display[columns])
        st.caption(f"أثر النماذج المحدود على الدرجة الفنية: {float(report.get('breakout_score_delta') or 0):+.2f}")


def _render_external_context(report: dict[str, Any]) -> None:
    lifecycle = report.get("external_signal_lifecycle") if isinstance(report.get("external_signal_lifecycle"), dict) else {}
    comparison = report.get("external_signal_comparison") if isinstance(report.get("external_signal_comparison"), dict) else {}
    with st.expander("🔗 المؤشر والبوت", expanded=False):
        if not lifecycle.get("available"):
            st.info("لا توجد أحداث محفوظة من SC-V90 أو SC-FXM لهذا الرمز والفاصل بعد.")
            st.caption("احفظ JSON من قسم «المؤشر والبوت» لتظهر دورة الخطة هنا.")
            return
        rows = [
            {"البند": "المصدر", "القيمة": lifecycle.get("source")},
            {"البند": "آخر حدث", "القيمة": lifecycle.get("event")},
            {"البند": "حالة الدورة", "القيمة": lifecycle.get("status")},
            {"البند": "الاتجاه", "القيمة": lifecycle.get("direction")},
            {"البند": "وقت الحدث", "القيمة": lifecycle.get("event_time")},
            {"البند": "الدخول", "القيمة": lifecycle.get("entry")},
            {"البند": "الوقف", "القيمة": lifecycle.get("stop")},
            {"البند": "الأهداف", "القيمة": lifecycle.get("targets")},
            {"البند": "الأحداث المحفوظة", "القيمة": lifecycle.get("events")},
        ]
        render_custom_table(pd.DataFrame(rows))
        if comparison.get("aligned"):
            st.success("الحدث الخارجي متوافق مع قرار أصولي الحالي.")
        elif comparison.get("conflicts"):
            st.warning(" — ".join(str(item) for item in comparison.get("conflicts") or []))
        st.caption("المؤشر والبوت دليلان خارجيان؛ تأثيرهما المباشر على قرار أصولي يظل صفرًا.")


def _render_data_lineage(report: dict[str, Any]) -> None:
    reliability = report.get("data_reliability") if isinstance(report.get("data_reliability"), dict) else {}
    price = (report.get("engine_meta") or {}).get("data_lineage") if isinstance(report.get("engine_meta"), dict) else {}
    financial = report.get("financial_data_lineage") if isinstance(report.get("financial_data_lineage"), dict) else {}
    with st.expander("🧾 مصادر القرار وجودة البيانات", expanded=False):
        rows = [
            {"الطبقة": "الأسعار والشموع", "المصدر": reliability.get("price_source"), "الجودة": reliability.get("price_score"), "الفترات/الشموع": price.get("rows")},
            {"الطبقة": "القوائم المالية", "المصدر": reliability.get("financial_source"), "الجودة": reliability.get("financial_score"), "الفترات/الشموع": (financial.get("quality") or {}).get("periods") if isinstance(financial.get("quality"), dict) else None},
        ]
        render_custom_table(pd.DataFrame(rows))
        attempts = list(price.get("provider_attempts") or []) if isinstance(price, dict) else []
        if attempts:
            st.markdown("**محاولات مزودي الأسعار:**")
            render_custom_table(pd.DataFrame(attempts))
        financial_attempts = list(financial.get("provider_attempts") or []) if isinstance(financial, dict) else []
        if financial_attempts:
            st.markdown("**محاولات مزودي القوائم:**")
            render_custom_table(pd.DataFrame(financial_attempts))


def _render_plan(report: dict[str, Any]) -> None:
    plan = report.get("risk_plan") if isinstance(report.get("risk_plan"), dict) else {}
    geometry = report.get("plan_geometry") if isinstance(report.get("plan_geometry"), dict) else {}
    with st.expander("الخطة التنفيذية المدققة", expanded=False):
        if plan.get("entry") is None:
            st.info("لا توجد خطة مكتملة.")
            return
        rows = [
            {"البند": "الدخول", "القيمة": plan.get("entry")},
            {"البند": "الوقف", "القيمة": plan.get("stop")},
            {"البند": "الهدف 1", "القيمة": plan.get("target1")},
            {"البند": "الهدف 2", "القيمة": plan.get("target2")},
            {"البند": "الهدف 3", "القيمة": plan.get("target3")},
            {"البند": "الإبطال", "القيمة": plan.get("invalidation")},
            {"البند": "صلاحية المرشح", "القيمة": f"{plan.get('expiry_bars')} شمعة"},
        ]
        render_custom_table(pd.DataFrame(rows))
        if geometry.get("valid"):
            st.success("اجتازت هندسة الخطة ترتيب الاتجاه والوقف والأهداف وحدود الفاصل.")
        else:
            st.warning(" — ".join(str(item) for item in geometry.get("issues") or ["الخطة غير مكتملة"]))


def _render_rules(symbol: str) -> None:
    key = _sym_key(symbol)
    with st.expander("🧠 قواعدي الخاصة", expanded=False):
        st.caption("القواعد تضيف دليلًا محدودًا ولا تتجاوز بوابات المخاطر أو شرط إغلاق الشمعة.")
        rule_text = st.text_area(
            "القاعدة",
            placeholder="مثال: اختراق مقاومة بإغلاق + حجم أعلى من المتوسط + وقف تحت الدعم",
            height=100,
            key=f"advisor_v5_rule:{key}",
        )
        if st.button("حفظ القاعدة", type="primary", key=f"advisor_v5_save:{key}"):
            if not rule_text.strip():
                st.warning("اكتب قاعدة محددة أولًا.")
            else:
                result = save_user_rule(rule_text, title="قاعدة من المستخدم", enabled=1)
                if isinstance(result, dict) and result.get("ok"):
                    st.success("تم حفظ القاعدة.")
                    _cache().clear()
                    st.rerun()
                else:
                    st.error(str((result or {}).get("reason") or "تعذر الحفظ"))
        rules = load_user_rules(enabled_only=True, max_rows=20) or []
        if rules:
            st.markdown("**القواعد النشطة:**")
            for rule in rules:
                st.write(f"- {rule.get('title', 'قاعدة')}: {rule.get('rule_text', '')}")


def render_advisor_tab(symbol: str, interval: str = "1d") -> None:
    st.subheader("🤖 المستشار الذكي V5")
    st.caption("قرار موحد يشرح الفني والمالي والنماذج ومصدر البيانات وتوافق المؤشر والبوت دون عرض تفاصيل تقنية حساسة.")
    left, right = st.columns([3, 1])
    run = left.button("تشغيل المستشار", type="primary", use_container_width=True, key=f"advisor_v5_run:{_sym_key(symbol)}:{interval}")
    refresh = right.button("إعادة الحساب", use_container_width=True, key=f"advisor_v5_refresh:{_sym_key(symbol)}:{interval}")
    if run or refresh:
        with st.spinner("جاري بناء التقرير ودمج النماذج ومصادر البيانات..."):
            _run(symbol, interval, refresh=refresh)
    payload = _cache().get(f"{symbol}|{interval}") or {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    if not report:
        st.info("اضغط «تشغيل المستشار» لعرض الرأي على الفاصل المختار.")
        _render_rules(symbol)
        return
    if report.get("__error__") or str(report.get("status") or "").lower() == "error":
        st.error(str(report.get("message") or "تعذر تشغيل المستشار بأمان"))
        return
    _render_summary(report, str(payload.get("generated_at") or "—"))
    _render_intelligence(report)
    _render_explanation(report)
    _render_breakouts(report)
    _render_external_context(report)
    _render_plan(report)
    _render_data_lineage(report)
    _render_rules(symbol)
