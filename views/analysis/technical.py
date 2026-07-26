"""Technical analysis UI v2.

Shows the real data source, separates direction from confidence, and only
presents actionable advanced signals generated from confirmed candles.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from components import render_custom_table
from market_data_v2 import get_chart_history, get_data_lineage
from technical_indicators.advanced import compute_advanced_technical_pack
from views.shared import _render_technical_chart_flex


def _bias_ar(value: Any) -> tuple[str, str]:
    key = str(value or "neutral").lower()
    if key == "bullish":
        return "إيجابي", "🟢"
    if key == "bearish":
        return "سلبي", "🔴"
    return "محايد/مختلط", "⚪"


def _quality(frame: pd.DataFrame) -> Dict[str, Any]:
    issues: List[str] = []
    if frame is None or frame.empty:
        return {"ok": False, "score": 0, "issues": ["لا توجد بيانات سعرية."], "rows": 0}
    required = {"Open", "High", "Low", "Close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        issues.append("أعمدة ناقصة: " + "، ".join(missing))
    if len(frame) < 220:
        issues.append("عدد الشموع أقل من 220؛ تقل موثوقية الاتجاهات طويلة الأجل.")
    if {"High", "Low"}.issubset(frame.columns):
        bad = int((pd.to_numeric(frame["High"], errors="coerce") < pd.to_numeric(frame["Low"], errors="coerce")).sum())
        if bad:
            issues.append(f"يوجد {bad} شموع بقيم High أقل من Low.")
    if {"Open", "High", "Low", "Close"}.issubset(frame.columns):
        invalid_prices = 0
        for col in ("Open", "High", "Low", "Close"):
            invalid_prices += int((pd.to_numeric(frame[col], errors="coerce").fillna(0) <= 0).sum())
        if invalid_prices:
            issues.append(f"يوجد {invalid_prices} قيم سعرية غير موجبة.")
    score = max(0, 100 - 18 * len(issues))
    return {"ok": not issues, "score": score, "issues": issues, "rows": len(frame)}


def _render_signal_table(signals: list[dict]) -> None:
    if not signals:
        st.info("لا توجد إشارة تنفيذية جديدة على آخر شمعة مغلقة.")
        return
    rows = []
    for signal in signals:
        rows.append(
            {
                "type": signal.get("type", "INFO"),
                "kind": signal.get("kind", ""),
                "price": signal.get("price"),
                "confirmation": signal.get("confirmation", "closed_candle"),
                "reason": signal.get("reason", ""),
            }
        )
    render_custom_table(
        pd.DataFrame(rows),
        [
            ("type", "الإشارة", "text"),
            ("kind", "النوع", "text"),
            ("price", "السعر", "money"),
            ("confirmation", "التأكيد", "text"),
            ("reason", "السبب", "text"),
        ],
    )


def _render_indicator(title: str, result: Dict[str, Any]) -> None:
    bias_text, bias_icon = _bias_ar(result.get("bias"))
    direction = int(result.get("direction_score") or 0)
    confidence = int(result.get("confidence") or 0)
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.metric("الاتجاه", f"{bias_icon} {bias_text}", f"{direction:+d}")
    with c2:
        st.metric("ثقة الإشارة", f"{confidence}%")
    with c3:
        st.info(result.get("summary") or "لا يوجد ملخص.")

    warnings = result.get("warnings") or []
    errors = result.get("errors") or []
    if warnings or errors:
        with st.expander("ملاحظات جودة الحساب"):
            for item in warnings:
                st.warning(item)
            for item in errors:
                st.error(item)

    evidence = result.get("evidence") or []
    if evidence:
        with st.expander("الأدلة"):
            for item in evidence:
                st.write(f"- {item}")

    _render_signal_table(result.get("signals") or [])

    features = result.get("features") or {}
    scalar_rows = [
        {"feature": key, "value": value}
        for key, value in features.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    ]
    if scalar_rows:
        with st.expander("التفاصيل الرقمية"):
            render_custom_table(pd.DataFrame(scalar_rows), [("feature", "البند", "text"), ("value", "القيمة", "auto")])


def view_technical(symbol: str, interval: str = "1d") -> None:
    st.subheader("📈 التحليل الفني")
    try:
        frame = get_chart_history(symbol, period="1y", interval=interval, years=5)
    except Exception as exc:
        st.error("تعذر جلب البيانات السعرية.")
        st.caption(str(exc))
        frame = pd.DataFrame()

    lineage = get_data_lineage(frame)
    quality = _quality(frame)
    source = lineage.get("source") or (frame.attrs.get("source") if isinstance(frame, pd.DataFrame) else "unknown")
    last_bar = str(frame.index[-1]) if isinstance(frame, pd.DataFrame) and not frame.empty else "—"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("المصدر", str(source or "غير معروف"))
    with c2:
        st.metric("آخر شمعة", last_bar)
    with c3:
        st.metric("عدد الشموع", quality["rows"])
    with c4:
        st.metric("جودة البيانات", f"{quality['score']}/100")

    if quality["issues"]:
        with st.expander("ملاحظات جودة البيانات", expanded=not quality["ok"]):
            for issue in quality["issues"]:
                st.write(f"- {issue}")

    tab_chart, tab_advanced = st.tabs(["الرسم الفني", "المؤشرات المتقدمة"])

    with tab_chart:
        try:
            _render_technical_chart_flex(symbol, period="1y", interval=interval)
        except Exception as exc:
            st.warning(f"تعذر عرض الرسم الفني المتقدم: {exc}")
            if not frame.empty:
                st.line_chart(pd.to_numeric(frame["Close"], errors="coerce"))

    with tab_advanced:
        if frame.empty:
            st.warning("لا توجد بيانات لحساب المؤشرات المتقدمة.")
            return
        with st.spinner("حساب المؤشرات من الشموع المغلقة..."):
            pack = compute_advanced_technical_pack(frame, symbol=symbol, timeframe=interval)

        bias_text, bias_icon = _bias_ar(pack.get("bias"))
        direction = int(pack.get("direction_score") or 0)
        confidence = int(pack.get("confidence") or 0)
        meta = pack.get("meta") or {}

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("الاتجاه المركب", f"{bias_icon} {bias_text}", f"{direction:+d}")
        with p2:
            st.metric("ثقة التحليل", f"{confidence}%")
        with p3:
            st.metric("شموع مؤكدة", int(meta.get("confirmed_rows") or 0))
        with p4:
            st.metric("استبعاد شمعة حية", "نعم" if meta.get("live_bar_excluded") else "لا")

        st.info(pack.get("summary") or "لا يوجد ملخص.")
        st.caption("درجة الاتجاه من -100 إلى +100، أما الثقة فمن 0 إلى 100. ارتفاع الثقة لا يعني أن الاتجاه صاعد.")

        for key, title in (
            ("rls_forecast", "1) الاتجاه التكيفي RLS"),
            ("chaos_wrsi", "2) RSI المتكيف مع اضطراب السوق"),
            ("volume_profile_clusters", "3) مناطق الحجم السعرية"),
            ("trendline_breakout", "4) اختراق وكسر خطوط الاتجاه"),
        ):
            with st.expander(title, expanded=key == "trendline_breakout"):
                _render_indicator(title, pack.get(key) or {})

        try:
            from ai_engine_core.db import save_advanced_indicators

            save_advanced_indicators(symbol=str(symbol), timeframe=str(interval), indicators=pack)
        except Exception:
            pass


def render_technical_tab(symbol: str, interval: str = "1d") -> None:
    view_technical(symbol, interval=interval)
