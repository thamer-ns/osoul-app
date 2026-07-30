"""On-demand market-bot analysis inside the Osoli analysis workspace."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ai_engine_core.bot_remote_analysis_v8 import request_bot_analysis
from components import render_custom_table, render_kpi


def _value(value: Any) -> str:
    if value in (None, ""):
        return "—"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def render_bot_remote_analysis(symbol: str, timeframe: str = "1d") -> None:
    st.subheader("🤖 تحليل محرك البوت المرتبط")
    st.caption(
        "يعمل عند الطلب فقط حتى لا يضيف زمنًا إلى فتح الصفحة. "
        "الطلب مصادق عليه عبر Channel معتم ولا يرسل رقم المستخدم أو المحفظة."
    )
    key = f"bot_remote_v8:{symbol}:{timeframe}"
    if st.button(
        "تشغيل تحليل البوت ومقارنته",
        type="primary",
        use_container_width=True,
        key=f"run_{key}",
    ):
        with st.spinner("تشغيل محرك البوت ضمن المهلة الآمنة..."):
            st.session_state[key] = request_bot_analysis(symbol, timeframe)

    result = st.session_state.get(key) or {}
    if not result:
        st.info("اضغط الزر لتشغيل التحليل المشترك على الرمز والفاصل الحاليين.")
        return
    if not result.get("ok"):
        reason = str(result.get("reason") or "unavailable")
        st.warning(f"تعذر تحليل البوت الآن — {reason}")
        return

    frame = result.get("frame") if isinstance(result.get("frame"), dict) else {}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("الاتجاه", _value(frame.get("trend")), "neutral", "🧭")
    with c2:
        render_kpi("الثقة", f"{int(frame.get('confidence') or 0)}%", "blue", "🎯")
    with c3:
        render_kpi(
            "الخطة",
            "صالحة" if frame.get("plan_valid") else "مراقبة",
            "success" if frame.get("plan_valid") else "warning",
            "📋",
        )
    with c4:
        render_kpi("المصدر", _value(frame.get("data_source")), "neutral", "🛰️")

    rows = [
        {"البند": "الحدث", "القيمة": _value(frame.get("event"))},
        {"البند": "حالة الخطة", "القيمة": _value(frame.get("plan_state"))},
        {"البند": "الدخول", "القيمة": _value(frame.get("entry"))},
        {"البند": "الوقف", "القيمة": _value(frame.get("stop"))},
        {"البند": "الأهداف", "القيمة": _value(frame.get("targets"))},
        {"البند": "الدعم", "القيمة": _value(frame.get("support"))},
        {"البند": "المقاومة", "القيمة": _value(frame.get("resistance"))},
        {"البند": "حداثة البيانات", "القيمة": _value(frame.get("data_age_seconds"))},
        {"البند": "عقد الربط", "القيمة": _value(result.get("contract"))},
    ]
    render_custom_table(pd.DataFrame(rows))
    reasons = [str(item) for item in frame.get("reasons") or []]
    warnings = [str(item) for item in frame.get("warnings") or []]
    if reasons:
        st.success("\n\n".join(reasons[:8]))
    if warnings:
        st.warning("\n\n".join(warnings[:8]))
    st.caption(
        "تحليل البوت مستقل للمقارنة والتأكيد؛ لا ينفذ أوامر ولا يغير صفقة المحفظة تلقائيًا."
    )


__all__ = ["render_bot_remote_analysis"]
