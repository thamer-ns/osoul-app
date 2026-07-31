"""Resilient single-page analysis and advisor presentation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

import streamlit as st

from views.shared import _generate_ai_report_flex, _sym_key

from .workspace_v18 import (
    _advisor_action,
    _cache,
    _cache_key,
    _decision,
    _levels,
    _mapping,
    _position_size,
    _render_advanced,
    _render_advisor,
    _render_decision_header,
    _render_plan,
    _render_prices,
    _render_scenarios,
    _report_error,
    _targets,
)

LOGGER = logging.getLogger(__name__)


def _generate(
    symbol: str,
    interval: str,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Generate and cache a report without allowing provider errors to crash UI."""
    cache = _cache()
    key = _cache_key(symbol, interval)
    if refresh:
        cache.pop(key, None)
    if key in cache:
        return _mapping(cache.get(key))

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        raw_report = _generate_ai_report_flex(symbol, timeframe=interval)
        report = raw_report if isinstance(raw_report, dict) else {
            "ok": False,
            "status": "error",
            "message": "أعاد محرك التحليل نتيجة غير صالحة.",
            "diagnostic_code": "analysis_invalid_payload",
        }
    except Exception:
        LOGGER.exception("Comprehensive analysis generation failed")
        report = {
            "ok": False,
            "status": "error",
            "message": (
                "تعذر إكمال التحليل من مصادر البيانات الحالية. "
                "لم تُنشأ صفقة أو توصية ناقصة."
            ),
            "diagnostic_code": "analysis_generation_failed",
        }

    payload = {"report": report, "generated_at": generated_at}
    cache[key] = payload
    st.session_state["analysis_workspace_v18_cache"] = cache
    return payload


def _safe_render_block(
    code: str,
    renderer: Callable[..., None],
    *args: Any,
) -> bool:
    try:
        renderer(*args)
        return True
    except Exception:
        LOGGER.exception("Analysis presentation block failed: %s", code)
        st.warning("تعذر عرض جزء من التفاصيل، لكن بقية التحليل ما زالت متاحة.")
        st.caption(f"رمز الجزء: {code}")
        return False


def render_decision_workspace(
    symbol: str,
    interval: str,
    finance: dict[str, Any] | None = None,
) -> None:
    """Render analysis, trade plan and advisor together without nested tabs."""
    finance = finance or {}
    st.subheader("التحليل الشامل")
    st.caption(
        "اتجاه صعود أو هبوط، خطة دخول ووقف وأهداف، ثم قرار مستشار مرتبط "
        "بمركزك ومحفظتك."
    )

    payload = _mapping(_cache().get(_cache_key(symbol, interval)))
    report = _mapping(payload.get("report"))
    button_label = "تحديث التحليل" if report else "حلل الآن"
    if st.button(
        button_label,
        type="primary",
        use_container_width=True,
        key=f"workspace_v20_run:{_sym_key(symbol)}:{interval}",
    ):
        with st.spinner("جاري تحليل الاتجاه والخطة والمخاطر..."):
            payload = _generate(symbol, interval, refresh=True)
            report = _mapping(payload.get("report"))

    if not report:
        st.info("اضغط «حلل الآن» لعرض القرار والخطة والمستشار.")
        return

    error = _report_error(report)
    if error:
        st.error(error)
        code = str(report.get("diagnostic_code") or "analysis_report_error")
        st.caption(f"رمز التشخيص: {code}")
        if st.button(
            "إعادة محاولة التحليل",
            use_container_width=True,
            key=f"workspace_v20_retry:{_sym_key(symbol)}:{interval}",
        ):
            _generate(symbol, interval, refresh=True)
            st.rerun()
        return

    _safe_render_block("decision_header", _render_decision_header, report)
    _safe_render_block("price_context", _render_prices, report)

    st.divider()
    _safe_render_block("trade_plan", _render_plan, report)
    _safe_render_block("scenarios", _render_scenarios, report)

    st.divider()
    _safe_render_block("advisor", _render_advisor, report, finance, symbol)
    _safe_render_block("advanced_details", _render_advanced, report)

    st.caption(
        f"آخر تحليل: {payload.get('generated_at', '—')} — التحليل تعليمي "
        "ولا يضمن الربح ولا ينفذ تداولًا."
    )


__all__ = [
    "_advisor_action",
    "_decision",
    "_generate",
    "_levels",
    "_position_size",
    "_targets",
    "render_decision_workspace",
]
