"""SC-V90/SC-FXM and Telegram market-bot integration workspace."""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd
import streamlit as st

from ai_engine_core.bot_bridge_v5 import (
    bot_health,
    bridge_configuration,
    forward_compass_payload,
    sync_bot_events,
)
from ai_engine_core.compass_contract import compare_compass_with_report, parse_compass_payload
from ai_engine_core.external_signal_journal_v5 import (
    lifecycle_snapshot,
    recent_external_events,
    record_external_event,
)
from components import render_custom_table, render_kpi
from views.shared import _generate_ai_report_flex, _sym_key

LOGGER = logging.getLogger(__name__)
_EVENT_LABELS = {
    "NL": "خطة صاعدة جديدة",
    "NS": "خطة هابطة جديدة",
    "T1": "تحقق الهدف الأول",
    "T2": "تحقق الهدف الثاني",
    "T3": "تحقق الهدف الثالث",
    "SL": "وقف مؤكد بالإغلاق",
    "C": "إلغاء الخطة",
    "FO": "كسر وهمي مؤكد",
}
_STATUS_LABELS = {
    "ACTIVE": "نشطة",
    "TARGET_1": "تحقق T1",
    "TARGET_2": "تحقق T2",
    "TARGET_3": "اكتملت الأهداف",
    "STOPPED": "توقفت",
    "CANCELLED": "ملغاة",
    "FAKEOUT": "كسر وهمي",
}
_REASON_LABELS = {
    "duplicate": "الحدث موجود مسبقًا ولم يُنشأ سجل جديد.",
    "missing_initial_event": "رُفض الحدث لأنه لا توجد خطة NL/NS سابقة بالمستويات نفسها.",
    "stale_or_out_of_order_event": "رُفض الحدث لأنه أقدم من آخر حدث محفوظ أو يحمل التوقيت نفسه.",
    "invalid_lifecycle_transition": "رُفض الحدث لأن ترتيب دورة الخطة غير صحيح.",
    "lifecycle_already_closed": "الخطة منتهية ولا تقبل أحداثًا جديدة.",
    "active_plan_already_exists": "توجد خطة نشطة بالمستويات نفسها.",
}


def _validated_cache_key(symbol: str, interval: str) -> str:
    return f"validated_external:{symbol}:{interval}"


def _sync_once(*, quiet: bool) -> dict[str, Any]:
    result = sync_bot_events(limit=100)
    if not quiet:
        if result.get("ok"):
            st.success(
                f"اكتملت المزامنة — جديد: {int(result.get('received') or 0)}، "
                f"مكرر: {int(result.get('duplicates') or 0)}"
            )
        elif result.get("reason") != "sync_not_configured":
            st.warning("تعذرت مزامنة تحديثات البوت الآن.")
    return result


@st.fragment(run_every="60s")
def _automatic_sync_fragment() -> None:
    config = bridge_configuration()
    if not config.get("sync_configured"):
        st.caption("المزامنة التلقائية غير مهيأة؛ يلزم SC_BOT_SYNC_TOKEN وSC_BOT_SYNC_SECRET.")
        return
    result = _sync_once(quiet=True)
    if result.get("ok"):
        received = int(result.get("received") or 0)
        st.caption(
            "🔄 مزامنة البوت تعمل كل 60 ثانية أثناء بقاء الصفحة مفتوحة"
            + (f" — استُقبل {received} تحديث جديد" if received else " — لا تحديثات جديدة")
        )
    else:
        st.caption("⚠️ تعذرت دورة المزامنة التلقائية الأخيرة؛ سيُعاد المحاولة تلقائيًا.")


def _render_bridge_status(symbol: str, interval: str) -> None:
    config = bridge_configuration()
    lifecycle = lifecycle_snapshot(symbol, interval)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mode = "ثنائي الاتجاه" if config.get("sync_configured") else "إرسال فقط" if config.get("configured") else "غير مهيأ"
        render_kpi("ربط البوت", mode, "success" if config.get("sync_configured") else "warning" if config.get("configured") else "neutral", "🤖")
    with c2:
        render_kpi("سجل المؤشر", "متاح" if lifecycle.get("available") else "لا أحداث", "blue", "🧭")
    with c3:
        render_kpi("حالة الدورة", _STATUS_LABELS.get(str(lifecycle.get("status")), str(lifecycle.get("status") or "—")), "neutral", "🔄")
    with c4:
        render_kpi("عدد الأحداث", str(lifecycle.get("events") or 0), "neutral", "🗂️")

    b1, b2 = st.columns(2)
    if b1.button("اختبار اتصال البوت", use_container_width=True, key=f"bot_health:{_sym_key(symbol)}:{interval}"):
        with st.spinner("فحص خدمة البوت..."):
            health = bot_health()
        st.session_state[f"bot_health_result:{symbol}"] = health
    if b2.button("مزامنة الآن", use_container_width=True, disabled=not bool(config.get("sync_configured")), key=f"bot_sync:{_sym_key(symbol)}:{interval}"):
        with st.spinner("جلب تحديثات دورة الصفقة من البوت..."):
            _sync_once(quiet=False)
        st.rerun()

    health = st.session_state.get(f"bot_health_result:{symbol}") or {}
    if health:
        if health.get("ok"):
            st.success(f"خدمة البوت تعمل — الإصدار {health.get('version') or 'غير معروف'}")
        else:
            st.warning("خدمة البوت غير متاحة أو لم تُضبط أسرار الربط بعد.")
    st.caption(
        "أصولي لا يخزن Telegram Bot Token. في وضع المزامنة يُستخدم Channel مشفر مشتق من المحفظة، "
        "ولا تُرسل أرقام المستخدم أو المحفظة إلى البوت."
    )
    _automatic_sync_fragment()


def _render_parsed(parsed: dict[str, Any], comparison: dict[str, Any] | None = None) -> None:
    geometry = parsed.get("geometry") if isinstance(parsed.get("geometry"), dict) else {}
    rows = [
        {"البند": "المصدر", "القيمة": parsed.get("source")},
        {"البند": "الحدث", "القيمة": _EVENT_LABELS.get(str(parsed.get("event")), parsed.get("event"))},
        {"البند": "الرمز", "القيمة": parsed.get("symbol")},
        {"البند": "الفاصل", "القيمة": parsed.get("timeframe")},
        {"البند": "الاتجاه", "القيمة": parsed.get("direction")},
        {"البند": "الدخول", "القيمة": parsed.get("entry")},
        {"البند": "الوقف", "القيمة": parsed.get("stop")},
        {"البند": "الأهداف", "القيمة": parsed.get("targets")},
        {"البند": "التوافق", "القيمة": parsed.get("confidence")},
        {"البند": "هندسة الخطة", "القيمة": "صالحة" if geometry.get("valid") else "غير مطلوبة للكسر الوهمي"},
        {"البند": "وقت الحدث", "القيمة": parsed.get("event_time")},
        {"البند": "حدث تاريخي", "القيمة": "نعم" if parsed.get("replay_event") else "لا"},
    ]
    render_custom_table(pd.DataFrame(rows))
    if comparison:
        if comparison.get("aligned"):
            st.success("الحدث يتطابق مع الرمز والفاصل واتجاه قرار أصولي الحالي.")
        elif comparison.get("conflicts"):
            st.warning(" — ".join(str(item) for item in comparison.get("conflicts") or []))
        st.caption("نتيجة المقارنة لا تغيّر قرار أصولي تلقائيًا.")


def _validate_payload(text: str, symbol: str, interval: str) -> dict[str, Any] | None:
    try:
        parsed = parse_compass_payload(text)
    except ValueError:
        LOGGER.info("Invalid integration payload rejected", exc_info=True)
        st.error("JSON غير صالح أو لا يطابق عقد SC-V90/SC-FXM الموحد.")
        return None
    report = _generate_ai_report_flex(symbol, timeframe=interval)
    comparison = compare_compass_with_report(parsed, report if isinstance(report, dict) else {})
    result = {"parsed": parsed, "comparison": comparison, "wire": text}
    st.session_state[_validated_cache_key(symbol, interval)] = result
    return result


def _render_ingest(symbol: str, interval: str) -> None:
    st.markdown("#### إدخال حدث من TradingView")
    st.caption(
        "الصق نص JSON الناتج من alert() في SC-V90-I أو SC-V90-D أو SC-FXM-V14. "
        "لا تلصق رابط Webhook أو أي Token."
    )
    text = st.text_area(
        "JSON الحدث",
        height=190,
        key=f"external_payload:{_sym_key(symbol)}:{interval}",
        placeholder='{"v":1,"s":"SC-V90-D","e":"NL",...}',
    )
    c1, c2, c3 = st.columns(3)
    validate = c1.button("تدقيق ومقارنة", type="primary", use_container_width=True, key=f"validate_external:{symbol}:{interval}")
    save = c2.button("حفظ في أصولي", use_container_width=True, key=f"save_external:{symbol}:{interval}")
    forward = c3.button("حفظ وإرسال للبوت", use_container_width=True, key=f"forward_external:{symbol}:{interval}")
    if validate:
        with st.spinner("تدقيق العقد ومقارنته بالتحليل الحالي..."):
            _validate_payload(text, symbol, interval)
    cached = st.session_state.get(_validated_cache_key(symbol, interval)) or {}
    if (save or forward) and not cached:
        cached = _validate_payload(text, symbol, interval) or {}
    if save or forward:
        parsed = cached.get("parsed") if isinstance(cached.get("parsed"), dict) else None
        if parsed:
            stored = record_external_event(parsed)
            if stored.get("ok") and stored.get("created"):
                st.success("تم حفظ حدث جديد داخل سجل أصولي المعزول للمستخدم.")
            elif stored.get("ok"):
                st.info(_REASON_LABELS.get(str(stored.get("reason")), "الحدث موجود مسبقًا."))
            else:
                st.error(_REASON_LABELS.get(str(stored.get("reason")), "تعذر حفظ الحدث أو أن تسلسله غير صالح."))
            if forward and stored.get("ok"):
                sent = forward_compass_payload(parsed)
                if sent.get("ok"):
                    verb = "قَبِل حدثًا جديدًا" if sent.get("created") else "أكد أن الحدث موجود"
                    st.success(f"البوت {verb} بنجاح.")
                elif sent.get("reason") == "historical_replay_not_forwarded":
                    st.warning("حُفظ الحدث التاريخي محليًا، لكنه لم يُرسل إلى البوت الحي.")
                else:
                    st.warning("حُفظ الحدث في أصولي، لكن خدمة البوت لم تستلمه. راجع إعدادات الربط.")
    cached = st.session_state.get(_validated_cache_key(symbol, interval)) or {}
    if cached.get("parsed"):
        _render_parsed(cached["parsed"], cached.get("comparison"))
        with st.expander("العقد المنظم", expanded=False):
            st.json(json.loads(json.dumps(cached["parsed"], ensure_ascii=False, default=str)))


def _render_journal(symbol: str, interval: str) -> None:
    st.markdown("#### سجل دورة المؤشر والبوت")
    frame = recent_external_events(symbol, interval, limit=100)
    if frame.empty:
        st.info("لا توجد أحداث محفوظة لهذا الرمز والفاصل.")
        return
    display = frame.copy()
    if "event_code" in display.columns:
        display["الحدث"] = display["event_code"].map(_EVENT_LABELS).fillna(display["event_code"])
    if "lifecycle_status" in display.columns:
        display["الحالة"] = display["lifecycle_status"].map(_STATUS_LABELS).fillna(display["lifecycle_status"])
    rename = {
        "source": "المصدر",
        "symbol": "الرمز",
        "timeframe": "الفاصل",
        "direction": "الاتجاه",
        "event_time": "وقت الحدث",
        "event_price": "سعر الحدث",
        "entry_price": "الدخول",
        "stop_price": "الوقف",
        "target1": "T1",
        "target2": "T2",
        "target3": "T3",
        "confidence": "الثقة",
        "geometry_valid": "هندسة صالحة",
        "remote_event_id": "رقم حدث البوت",
    }
    display = display.rename(columns=rename)
    columns = [column for column in ["وقت الحدث", "المصدر", "الحدث", "الحالة", "الاتجاه", "سعر الحدث", "الدخول", "الوقف", "T1", "T2", "T3", "الثقة", "هندسة صالحة", "رقم حدث البوت"] if column in display.columns]
    render_custom_table(display[columns])


def render_integration_workspace(symbol: str, interval: str = "1d") -> None:
    st.subheader("🔗 المؤشر والبوت داخل أصولي")
    st.caption(
        "تكامل مرتب زمنيًا لدورة SC-V90 وSC-FXM مع إرسال اختياري ومزامنة تلقائية لتحديثات البوت. "
        "لا يوجد تنفيذ أوامر تداول."
    )
    _render_bridge_status(symbol, interval)
    tab1, tab2 = st.tabs(["إدخال ومقارنة", "سجل الأحداث"])
    with tab1:
        _render_ingest(symbol, interval)
    with tab2:
        _render_journal(symbol, interval)
