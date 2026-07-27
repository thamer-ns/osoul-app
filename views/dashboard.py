"""Fast, money-flow-aware portfolio dashboard.

The first paint contains only database-backed KPIs.  External market calls,
Plotly imports and multi-symbol historical reconstruction are loaded explicitly
by the user so ordinary navigation stays responsive.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ai_engine_core.portfolio import calculate_portfolio_risk_score
from components import render_kpi, safe_fmt
from views.utils import safe_status_series

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
}


def _sf(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _style_figure(fig, *, legend_horizontal: bool = False):
    legend = dict(
        font=dict(family="Cairo, Tahoma, Arial", size=12),
        traceorder="normal",
    )
    if legend_horizontal:
        legend.update(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        )
    fig.update_layout(
        font=dict(family="Cairo, Tahoma, Arial", color="#334155"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=24, r=24, t=54, b=34),
        legend=legend,
        hoverlabel=dict(font_family="Cairo, Tahoma, Arial"),
    )
    return fig


@st.cache_data(ttl=300, max_entries=16, show_spinner=False)
def _cached_tasi_snapshot() -> tuple[object, object]:
    from market_data import get_tasi_data

    try:
        return get_tasi_data()
    except Exception:
        return None, None


@st.cache_data(ttl=600, max_entries=64, show_spinner=False)
def _cached_equity_curve(
    cache_key: str,
    _trades: pd.DataFrame,
    _deposits: pd.DataFrame,
    _withdrawals: pd.DataFrame,
    _returnsgrants: pd.DataFrame,
    days: int = 365,
) -> pd.DataFrame:
    """Build the expensive history only after the user requests it."""
    _ = cache_key
    from analytics import compute_portfolio_equity_curve

    return compute_portfolio_equity_curve(
        trades=_trades,
        deposits=_deposits,
        withdrawals=_withdrawals,
        returnsgrants=_returnsgrants,
        days=days,
    )


def _allocation_frame(trades: pd.DataFrame, cash: float) -> pd.DataFrame:
    status = safe_status_series(trades)
    open_trades = (
        trades[status == "open"].copy()
        if isinstance(trades, pd.DataFrame) and len(status)
        else pd.DataFrame()
    )
    invest_value = spec_value = sukuk_value = 0.0
    if not open_trades.empty and "market_value" in open_trades.columns:
        market_series = pd.to_numeric(
            open_trades["market_value"],
            errors="coerce",
        ).fillna(0.0)
        strategies = open_trades.get(
            "strategy",
            pd.Series("", index=open_trades.index),
        ).astype(str)
        asset_types = open_trades.get(
            "asset_type",
            pd.Series("", index=open_trades.index),
        ).astype(str).str.lower()
        invest_value = float(
            market_series[strategies.str.contains("استثمار", na=False)].sum()
        )
        spec_value = float(
            market_series[strategies.str.contains("مضاربة", na=False)].sum()
        )
        sukuk_value = float(market_series[asset_types.eq("sukuk")].sum())

    allocation = pd.DataFrame(
        {
            "الأصل": ["استثمار", "مضاربة", "صكوك", "كاش"],
            "القيمة": [invest_value, spec_value, sukuk_value, cash],
        }
    )
    return allocation[allocation["القيمة"] > 0]


def _render_tasi_card(loaded: bool) -> None:
    tasi = tasi_change = None
    if loaded:
        with st.spinner("جاري تحميل بيانات السوق..."):
            tasi, tasi_change = _cached_tasi_snapshot()
    change_text = "—" if tasi_change is None else f"{float(tasi_change):+.2f}%"
    value_text = "—" if tasi is None else safe_fmt(tasi)
    note = "آخر قراءة مخزنة" if loaded else "يُحمّل عند الطلب لتسريع الصفحة"
    st.markdown(
        f"""
        <div class="tasi-card" dir="rtl">
          <div>
            <div style="opacity:.9">المؤشر العام تاسي</div>
            <div style="font-size:clamp(1.45rem,2.5vw,2.1rem);font-weight:900;direction:ltr;text-align:right">{value_text}</div>
            <div style="font-size:.72rem;opacity:.78">{note}</div>
          </div>
          <div style="background:rgba(255,255,255,.2);padding:5px 13px;border-radius:10px;font-weight:bold;direction:ltr">{change_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_advanced_charts(fin: dict, trades: pd.DataFrame, cash: float) -> None:
    import plotly.express as px

    allocation = _allocation_frame(trades, cash)
    left, right = st.columns(2)
    with left:
        st.subheader("توزيع الأصول")
        if allocation.empty:
            st.info("لا توجد أصول موزعة")
        else:
            figure = px.pie(
                allocation,
                values="القيمة",
                names="الأصل",
                hole=0.42,
            )
            figure.update_traces(
                textposition="inside",
                textinfo="percent",
                hovertemplate="%{label}<br>%{value:,.2f}<extra></extra>",
            )
            _style_figure(figure)
            st.plotly_chart(figure, width="stretch", config=PLOTLY_CONFIG)

    with right:
        st.subheader("القيمة والعائد الحقيقي")
        with st.spinner("جاري بناء المنحنى التاريخي..."):
            curve = _cached_equity_curve(
                str(fin.get("_cache_key") or "session"),
                trades,
                fin.get("deposits", pd.DataFrame()),
                fin.get("withdrawals", pd.DataFrame()),
                fin.get("returns", pd.DataFrame()),
                365,
            )
        if curve is None or curve.empty:
            st.info("لا توجد بيانات كافية لبناء منحنى القيمة")
        else:
            chart = curve[["date", "equity", "net_contributions"]].melt(
                id_vars="date",
                var_name="السلسلة",
                value_name="القيمة",
            )
            chart["السلسلة"] = chart["السلسلة"].map(
                {
                    "equity": "قيمة المحفظة",
                    "net_contributions": "صافي الإيداعات",
                }
            )
            figure = px.line(
                chart,
                x="date",
                y="القيمة",
                color="السلسلة",
            )
            figure.update_xaxes(title_text="")
            figure.update_yaxes(title_text="القيمة (ر.س)", tickformat=",")
            _style_figure(figure, legend_horizontal=True)
            st.plotly_chart(figure, width="stretch", config=PLOTLY_CONFIG)
            last_return = float(curve["cumulative_return"].iloc[-1]) * 100
            stale = int(curve["stale_price_count"].iloc[-1])
            st.caption(
                f"العائد المرجح زمنيًا خلال الفترة: {last_return:.2f}%"
                + (
                    f" — أسعار احتياطية لعدد {stale} رموز"
                    if stale
                    else ""
                )
            )


def view_dashboard(fin):
    fin = fin or {}
    trades = fin.get("all_trades", pd.DataFrame())
    market_value = _sf(fin.get("market_val_open"))
    cash = _sf(fin.get("cash"))
    total_assets = market_value + cash
    cash_pct = cash / total_assets * 100 if total_assets > 0 else 0.0

    try:
        risk_score = calculate_portfolio_risk_score(trades, cash_pct)
    except Exception:
        risk_score = None
    risk_label = (
        "غير متاح"
        if risk_score is None
        else "منخفضة"
        if risk_score < 40
        else "عالية"
        if risk_score > 70
        else "متوسطة"
    )
    risk_colour = (
        "neutral"
        if risk_score is None
        else "success"
        if risk_score < 40
        else "danger"
        if risk_score > 70
        else "neutral"
    )

    advanced_key = "_dashboard_advanced_loaded"
    advanced_loaded = bool(st.session_state.get(advanced_key, False))

    tasi_col, risk_col = st.columns([3, 1])
    with tasi_col:
        _render_tasi_card(advanced_loaded)
    with risk_col:
        render_kpi(
            f"المخاطرة ({risk_label})",
            "—" if risk_score is None else f"{float(risk_score):.0f}/100",
            risk_colour,
            "🛡️",
        )

    total_pl = _sf(fin.get("unrealized_pl")) + _sf(fin.get("realized_pl"))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c2:
        render_kpi("القيمة السوقية", safe_fmt(market_value), "blue", "📊")
    with c3:
        render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(cash), "blue", "💵")
    with c4:
        render_kpi(
            "صافي الربح",
            safe_fmt(total_pl),
            "success" if total_pl >= 0 else "danger",
            "📈",
        )

    with st.expander("تفاصيل الأداء والمراكز", expanded=False):
        cost = _sf(fin.get("cost_open"))
        unrealised = _sf(fin.get("unrealized_pl"))
        open_return = unrealised / cost * 100 if cost else 0.0
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            render_kpi("تكلفة المراكز", safe_fmt(cost), "neutral")
        with d2:
            render_kpi(
                "الربح غير المحقق",
                safe_fmt(unrealised),
                "success" if unrealised >= 0 else "danger",
            )
        with d3:
            render_kpi(
                "عائد المراكز",
                f"{open_return:.2f}%",
                "success" if open_return >= 0 else "danger",
            )
        with d4:
            render_kpi(
                "صافي الإيداعات",
                safe_fmt(
                    _sf(fin.get("total_deposited"))
                    - _sf(fin.get("total_withdrawn"))
                ),
                "neutral",
            )

    if trades is None or trades.empty:
        st.info("مرحبًا بك. ابدأ بإضافة الإيداعات والصفقات.")
        return

    if not advanced_loaded:
        st.info(
            "تم فتح الصفحة بالوضع السريع. بيانات تاسي والرسوم التاريخية "
            "لا تُحمّل من الشبكة إلا عند طلبها."
        )
        if st.button(
            "تحميل بيانات السوق والرسوم المتقدمة",
            icon="📈",
            type="secondary",
            use_container_width=True,
            key="dashboard_load_advanced",
        ):
            st.session_state[advanced_key] = True
            st.rerun()
        return

    if st.button(
        "إخفاء الرسوم والعودة للوضع السريع",
        icon="⚡",
        use_container_width=True,
        key="dashboard_hide_advanced",
    ):
        st.session_state[advanced_key] = False
        st.rerun()

    _render_advanced_charts(fin, trades, cash)
