"""Streamlit presentation for separate completed-candle and live prices."""
from __future__ import annotations

import math
import threading
from typing import Any

_LOCK = threading.RLock()
_INSTALLED = False


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _closed_price(report: dict[str, Any]) -> float | None:
    features = report.get("features")
    features = features if isinstance(features, dict) else {}
    pack = report.get("sc_feature_pack")
    pack = pack if isinstance(pack, dict) else {}
    meta = report.get("engine_meta")
    meta = meta if isinstance(meta, dict) else {}
    lineage = meta.get("data_lineage")
    lineage = lineage if isinstance(lineage, dict) else {}
    for value in (
        report.get("closed_candle_price"),
        report.get("price"),
        features.get("closed_price"),
        features.get("close"),
        features.get("price"),
        pack.get("last_close"),
        pack.get("price"),
        lineage.get("close_price"),
        lineage.get("last_close"),
    ):
        number = _finite(value)
        if number is not None:
            return number
    return None


def _age(value: Any) -> str:
    try:
        seconds = max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return "غير معلن"
    if seconds < 60:
        return f"{seconds} ثانية"
    if seconds < 3600:
        return f"{math.ceil(seconds / 60)} دقيقة"
    if seconds < 86_400:
        return f"{math.ceil(seconds / 3600)} ساعة"
    return f"{math.ceil(seconds / 86_400)} يوم"


def install_live_market_ui_v17() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        from views.analysis import advisor_v5

        previous = advisor_v5._render_data_lineage  # noqa: SLF001
        if getattr(previous, "_osoli_live_ui_v17", False):
            _INSTALLED = True
            return

        def render(report: dict[str, Any]) -> None:
            previous(report)
            live = report.get("live_quote_context")
            live = live if isinstance(live, dict) else {}
            if not live:
                return
            import pandas as pd
            import streamlit as st

            from components import render_custom_table

            closed = _closed_price(report)
            live_price = _finite(live.get("price"))
            source_count = int(live.get("source_count") or 0)
            comparison = str(live.get("comparison_label") or "")
            if not comparison:
                spread = _finite(
                    live.get("source_spread_pct", live.get("source_agreement_pct"))
                )
                comparison = (
                    "مصدر واحد — لا يمكن قياس اتفاق المصادر"
                    if source_count <= 1
                    else f"فارق المصادر {spread:.2f}%"
                    if spread is not None
                    else "المقارنة غير متاحة"
                )
            with st.expander("💹 إغلاق الشمعة والسعر السياقي", expanded=True):
                rows = [
                    {
                        "البيان": "إغلاق الشمعة المعتمد",
                        "السعر": closed if closed is not None else "غير متاح",
                        "المصدر": (
                            (report.get("data_reliability") or {}).get("price_source")
                            if isinstance(report.get("data_reliability"), dict)
                            else "غير محدد"
                        ),
                        "العمر/الحالة": "أساس القرار الفني",
                    },
                    {
                        "البيان": "السعر السياقي الحالي",
                        "السعر": live_price if live_price is not None else "غير متاح",
                        "المصدر": live.get("source") or "غير محدد",
                        "العمر/الحالة": (
                            f"{_age(live.get('quote_age_seconds'))} — "
                            f"{live.get('delay_status') or 'غير معلن'}"
                        ),
                    },
                ]
                render_custom_table(pd.DataFrame(rows))
                st.caption(comparison)
                st.info(
                    "السعر السياقي أضيف بعد القرار النهائي؛ لا يغير الاتجاه أو "
                    "التأهيل أو الدخول أو الوقف أو الأهداف، ولا يُحفظ بدل إغلاق الشمعة."
                )

        render._osoli_live_ui_v17 = True  # type: ignore[attr-defined]
        advisor_v5._render_data_lineage = render  # noqa: SLF001
        _INSTALLED = True


__all__ = ["install_live_market_ui_v17"]
