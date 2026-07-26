"""Osoli v2 dashboard with an actual NAV curve."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_v2 import compute_portfolio_equity_curve
from components import render_kpi, safe_fmt
from market_data_v2 import get_tasi_data

try:
    from ai_engine_core.portfolio import calculate_portfolio_risk_score
except Exception:  # pragma: no cover
    calculate_portfolio_risk_score = None


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def view_dashboard(fin: dict) -> None:
    try:
        tasi_price, tasi_change = get_tasi_data()
    except Exception:
        tasi_price, tasi_change = None, None

    all_trades = fin.get("all_trades", pd.DataFrame())
    open_positions = fin.get("open_positions_df", pd.DataFrame())
    total_assets = _num(fin.get("portfolio_value"))
    cash = _num(fin.get("cash"))
    cash_pct = _num(fin.get("cash_pct"))
    total_pl = _num(fin.get("unrealized_pl")) + _num(fin.get("realized_pl"))

    risk_score = None
    if callable(calculate_portfolio_risk_score) and not open_positions.empty:
        try:
            risk_score = float(calculate_portfolio_risk_score(open_positions, cash_pct))
        except Exception:
            risk_score = None

    left, right = st.columns([3, 1])
    with left:
        change_text = "—" if tasi_change is None else f"{tasi_change:+.2f}%"
        st.markdown(
            f"""
            <div class="tasi-card">
              <div>
                <div style="opacity:.9">المؤشر العام السعودي TASI</div>
                <div style="font-size:2.4rem;font-weight:900">{safe_fmt(tasi_price)}</div>
              </div>
              <div style="background:rgba(255,255,255,.2);padding:6px 14px;border-radius:10px">
                {change_text}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        render_kpi(
            "درجة المخاطر",
            "غير متاح" if risk_score is None else f"{risk_score:.0f}/100",
            "neutral" if risk_score is None else ("danger" if risk_score >= 70 else "success"),
            "🛡️",
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c2:
        render_kpi("القيمة السوقية", safe_fmt(fin.get("market_val_open", 0)), "blue", "📊")
    with c3:
        render_kpi("السيولة", f"{safe_fmt(cash)} ({cash_pct:.1f}%)", "blue", "💵")
    with c4:
        render_kpi("صافي الربح", safe_fmt(total_pl), "success" if total_pl >= 0 else "danger", "📈")

    data_quality = fin.get("data_quality") or {}
    notes = data_quality.get("notes") or []
    if notes:
        with st.expander("⚠️ ملاحظات جودة البيانات", expanded=True):
            for note in notes:
                st.write(f"- {note}")

    st.markdown("---")
    allocation = []
    if not open_positions.empty and "market_value" in open_positions.columns:
        strategy = open_positions["strategy"].astype(str) if "strategy" in open_positions.columns else pd.Series("", index=open_positions.index)
        asset_type = open_positions["asset_type"].astype(str) if "asset_type" in open_positions.columns else pd.Series("", index=open_positions.index)
        for label, mask in (
            ("استثمار", strategy.str.contains("استثمار", na=False)),
            ("مضاربة", strategy.str.contains("مضاربة", na=False)),
            ("صكوك", asset_type.str.lower().eq("sukuk")),
        ):
            value = float(open_positions.loc[mask, "market_value"].sum())
            if value > 0:
                allocation.append({"الأصل": label, "القيمة": value})
    if cash > 0:
        allocation.append({"الأصل": "سيولة", "القيمة": cash})

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.subheader("توزيع الأصول")
        if allocation:
            frame = pd.DataFrame(allocation)
            st.plotly_chart(px.pie(frame, values="القيمة", names="الأصل", hole=0.42), use_container_width=True)
        else:
            st.info("لا توجد أصول كافية للرسم.")

    with chart_right:
        st.subheader("القيمة التاريخية للمحفظة NAV")
        curve = compute_portfolio_equity_curve(
            all_trades,
            fin.get("deposits", pd.DataFrame()),
            fin.get("withdrawals", pd.DataFrame()),
            fin.get("returns", pd.DataFrame()),
            days=365,
        )
        if not curve.empty:
            plot_frame = curve[["date", "equity"]].rename(columns={"date": "التاريخ", "equity": "قيمة المحفظة"})
            st.plotly_chart(px.line(plot_frame, x="التاريخ", y="قيمة المحفظة"), use_container_width=True)
            missing = int(curve["missing_prices"].max()) if "missing_prices" in curve.columns else 0
            if missing:
                st.caption(f"تنبيه: استُخدم سعر احتياطي في بعض الأيام لعدد يصل إلى {missing} من المراكز.")
        else:
            st.info("لا توجد بيانات تاريخية كافية.")

    with st.expander("تفاصيل الأداء"):
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            render_kpi("الربح غير المحقق", safe_fmt(fin.get("unrealized_pl", 0)), "neutral")
        with d2:
            render_kpi("الربح المحقق", safe_fmt(fin.get("realized_pl", 0)), "neutral")
        with d3:
            xirr = fin.get("xirr")
            render_kpi("العائد المرجح نقديًا XIRR", "—" if xirr is None else f"{xirr * 100:.2f}%", "blue")
        with d4:
            render_kpi("صافي الإيداعات", safe_fmt(_num(fin.get("total_deposited")) - _num(fin.get("total_withdrawn"))), "neutral")
