"""Structured advisor presentation for the v4 analysis contract."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi
from views.shared import _generate_ai_report_flex, _sym_key, load_user_rules, save_user_rule


def _cache() -> dict[str, Any]:
    value = st.session_state.get("advisor_v4_cache")
    if not isinstance(value, dict):
        value = {}
        st.session_state["advisor_v4_cache"] = value
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
    st.session_state["advisor_v4_cache"] = cache
    return cache[key]


def _render_summary(report: dict[str, Any], generated_at: str) -> None:
    consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
    status = str(report.get("lifecycle_status") or "NO_SETUP")
    direction = str(report.get("direction") or "neutral")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("رأي المستشار", str(report.get("analysis_stage") or "مراقبة"), "blue", "🤖")
    with c2:
        render_kpi("الاتجاه", "صاعد" if direction == "buy" else "هابط" if direction == "sell" else "محايد", "neutral", "↕️")
    with c3:
        render_kpi("الثقة", f"{float(report.get('confidence') or 0):.0f}%", "neutral", "🎯")
    with c4:
        render_kpi("المدارس", str(consensus.get("school_count") or 0), "neutral", "🏫")
    st.subheader(str(report.get("recommendation") or "لا توجد نتيجة"))
    st.write(str(report.get("strategy") or ""))
    st.caption(f"الحالة التنفيذية: {status} — التوليد: {generated_at}")


def _render_explanation(report: dict[str, Any]) -> None:
    consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
    left, right = st.columns(2)
    with left:
        st.markdown("#### لماذا ظهر هذا الرأي؟")
        for item in (report.get("top_evidence") or [])[:8]:
            st.write(f"- {item}")
    with right:
        st.markdown("#### ما الذي قد يفسده؟")
        for item in (report.get("top_risks") or [])[:8]:
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
            key=f"advisor_v4_rule:{key}",
        )
        if st.button("حفظ القاعدة", type="primary", key=f"advisor_v4_save:{key}"):
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
    st.subheader("🤖 المستشار الذكي")
    st.caption("شرح القرار الموحد بلغة واضحة. لا يعرض Stack Trace أو بيانات داخلية حساسة للمستخدم.")
    left, right = st.columns([3, 1])
    run = left.button("تشغيل المستشار", type="primary", use_container_width=True, key=f"advisor_v4_run:{_sym_key(symbol)}:{interval}")
    refresh = right.button("إعادة الحساب", use_container_width=True, key=f"advisor_v4_refresh:{_sym_key(symbol)}:{interval}")
    if run or refresh:
        with st.spinner("جاري بناء التقرير..."):
            _run(symbol, interval, refresh=refresh)
    payload = _cache().get(f"{symbol}|{interval}") or {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    if not report:
        st.info("اضغط «تشغيل المستشار» لعرض الرأي على الفاصل المختار.")
        _render_rules(symbol)
        return
    if report.get("__error__") or str(report.get("status") or "").lower() == "error":
        st.error(str(report.get("message") or report.get("__error__") or "تعذر تشغيل المستشار"))
        return
    _render_summary(report, str(payload.get("generated_at") or "—"))
    _render_explanation(report)
    _render_plan(report)
    _render_rules(symbol)
