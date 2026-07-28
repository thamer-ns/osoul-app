"""Financial dashboard v5 with source lineage and quality gates."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi
from financial_analysis.store import get_stored_financials_df
from financial_providers_v5 import assess_summary_quality, configured_financial_order

from .financial import render_financial_dashboard_ui as _render_legacy_dashboard


def _lineage(frame: pd.DataFrame) -> dict[str, Any]:
    attrs = dict(getattr(frame, "attrs", {}) or {}) if isinstance(frame, pd.DataFrame) else {}
    value = attrs.get("financial_lineage")
    return dict(value) if isinstance(value, dict) else {}


def _render_source_panel(symbol: str) -> None:
    annual = get_stored_financials_df(symbol, "Annual")
    quarterly = get_stored_financials_df(symbol, "Quarterly")
    selected = annual if isinstance(annual, pd.DataFrame) and not annual.empty else quarterly
    period = "سنوي" if selected is annual and not annual.empty else "ربعي"
    lineage = _lineage(selected)
    quality = lineage.get("quality") if isinstance(lineage.get("quality"), dict) else assess_summary_quality(selected)
    source = str(lineage.get("source") or (selected.iloc[0].get("source") if not selected.empty and "source" in selected.columns else "غير متاح"))
    currency = str(quality.get("currency") or (selected.iloc[0].get("currency") if not selected.empty and "currency" in selected.columns else "—"))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("مصدر القوائم", source, "blue", "🗄️")
    with c2:
        render_kpi("جودة القوائم", f"{int(quality.get('score') or 0)}/100", "success" if quality.get("pass") else "warning", "🧾")
    with c3:
        render_kpi("الفترات", str(int(quality.get("periods") or len(selected))), "neutral", "📅")
    with c4:
        render_kpi("الدورية / العملة", f"{period} — {currency or '—'}", "neutral", "💱")
    if not quality.get("pass"):
        st.warning("التحليل المالي سيبقى محجوبًا أو منخفض الثقة حتى تتوفر فترتان صالحـتان وبنود أساسية متسقة.")
    st.caption(
        "الأولوية: البيانات المحفوظة أو المدخلة يدويًا، ثم "
        + " ← ".join(configured_financial_order())
        + ". القيم الناقصة لا تتحول إلى أصفار مصطنعة."
    )
    attempts = list(lineage.get("provider_attempts") or [])
    with st.expander("تفاصيل مزودي القوائم", expanded=False):
        if attempts:
            rows = []
            for item in attempts:
                rows.append(
                    {
                        "المزود": item.get("provider"),
                        "النتيجة": "نجح" if item.get("ok") else "لم يُعتمد",
                        "الجودة": item.get("quality_score"),
                        "الفترات": item.get("periods"),
                        "الرمز المحلول": item.get("resolved_symbol") or "—",
                        "الزمن ms": item.get("elapsed_ms"),
                        "السبب": item.get("reason") or "—",
                    }
                )
            render_custom_table(pd.DataFrame(rows))
        else:
            st.caption("تم استخدام البيانات المحلية؛ لم تكن هناك حاجة لمزود خارجي أو لم تُضبط مفاتيحه.")
        if quality.get("issues"):
            st.markdown("**ملاحظات الجودة:**")
            for issue in quality.get("issues") or []:
                st.write(f"- {issue}")


def render_financial_dashboard_ui(symbol: str) -> None:
    st.subheader("💰 التحليل المالي متعدد المصادر")
    _render_source_panel(symbol)
    st.divider()
    _render_legacy_dashboard(symbol)


__all__ = ["render_financial_dashboard_ui"]
