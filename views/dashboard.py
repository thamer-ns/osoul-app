#views/dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px

from components import render_kpi, safe_fmt
from market_data import get_tasi_data
from views.shared import _safe_status_series, calculate_portfolio_risk_score
from analytics import generate_equity_curve

def view_dashboard(fin):
    try:
        tp, tc = get_tasi_data()
    except Exception:
        tp, tc = 0, 0

    ar = "🔼" if tc >= 0 else "🔽"
    df = fin.get("all_trades", pd.DataFrame())

    total_assets = float(fin.get("market_val_open", 0)) + float(fin.get("cash", 0))
    cash_pct = (float(fin.get("cash", 0)) / total_assets * 100) if total_assets else 0

    # قد يرجع None إذا كان محرك المخاطر غير جاهز/حدث خطأ
    risk_score = calculate_portfolio_risk_score(df, cash_pct)
    if risk_score is None:
        risk_score = 0
        risk_color = "neutral"
        risk_label = "غير متاح"
    else:
        risk_color = "success" if risk_score < 40 else "danger" if risk_score > 70 else "neutral"
        risk_label = "منخفضة" if risk_score < 40 else "عالية" if risk_score > 70 else "متوسطة"

    c_tasi, c_risk = st.columns([3, 1])
    with c_tasi:
        st.markdown(
            f"""
            <div class="tasi-card">
                <div>
                    <div style="opacity:0.9;">المؤشر العام (TASI)</div>
                    <div style="font-size:2.5rem; font-weight:900;">{safe_fmt(tp)}</div>
                </div>
                <div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">
                    {ar} {tc:.2f}%
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c_risk:
        render_kpi(f"المخاطرة ({risk_label})", f"{risk_score}/100", risk_color, "🛡️")

    # -------------------------------
    # نظرة عامة (أوضح وأقل ازدحام)
    # -------------------------------
    total_pl = float(fin.get("unrealized_pl", 0)) + float(fin.get("realized_pl", 0))
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with m2:
        render_kpi("القيمة السوقية", safe_fmt(fin.get("market_val_open", 0)), "blue", "📊")
    with m3:
        render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(fin.get("cash", 0)), "blue", "💵")
    with m4:
        render_kpi("صافي الربح الكلي", safe_fmt(total_pl), "success" if total_pl >= 0 else "danger", "📈")

    # تفاصيل إضافية داخل Expander بدل تشتيت الشاشة الرئيسية
    with st.expander("تفاصيل المراكز المفتوحة", expanded=False):
        open_pct = (float(fin.get("unrealized_pl", 0)) / float(fin.get("cost_open", 0)) * 100) if float(fin.get("cost_open", 0)) else 0
        d1, d2, d3, d4 = st.columns(4)
        with d1: render_kpi("التكلفة", safe_fmt(fin.get("cost_open", 0)), "neutral")
        with d2: render_kpi("الربح الورقي", safe_fmt(fin.get("unrealized_pl", 0)), "success" if float(fin.get("unrealized_pl", 0)) >= 0 else "danger")
        with d3: render_kpi("النمو", f"{open_pct:.2f}%", "success" if open_pct >= 0 else "danger")
        with d4: render_kpi("صافي الإيداعات", safe_fmt(fin.get("total_deposited", 0) - fin.get("total_withdrawn", 0)), "neutral", "🏗️")

    st.markdown("---")

    if not df.empty:
        status = _safe_status_series(df)
        closed_df = df[status.isin(["close", "closed"])].copy() if len(status) else pd.DataFrame()
        closed_cost = float(closed_df["total_cost"].sum()) if (not closed_df.empty and "total_cost" in closed_df.columns) else 0
        closed_sales = float(closed_df["market_value"].sum()) if (not closed_df.empty and "market_value" in closed_df.columns) else 0
        closed_pl = float(fin.get("realized_pl", 0))
        closed_pct = (closed_pl / closed_cost * 100) if closed_cost else 0.0
    else:
        closed_cost = closed_sales = closed_pl = closed_pct = 0

    with st.expander("📜 ملخص الصفقات المنفذة (Executed)", expanded=False):
        x1, x2, x3, x4 = st.columns(4)
        with x1: render_kpi("رأس المال المسترد", safe_fmt(closed_cost), "neutral", "↩️")
        with x2: render_kpi("السيولة العائدة", safe_fmt(closed_sales), "blue", "📥")
        with x3: render_kpi("الربح المحقق", safe_fmt(closed_pl), "success" if closed_pl >= 0 else "danger", "✅")
        with x4: render_kpi("العائد المحقق", f"{closed_pct:.2f}%", "success" if closed_pct >= 0 else "danger", "٪")

    st.markdown("---")

    if not df.empty and "status" in df.columns:
        status = _safe_status_series(df)
        open_trades = df[status == "open"].copy()
        invest_val = 0
        spec_val = 0
        sukuk_val = 0

        try:
            if "strategy" in open_trades.columns and "market_value" in open_trades.columns:
                invest_val = open_trades[open_trades["strategy"].astype(str).str.contains("استثمار", na=False)]["market_value"].sum()
                spec_val = open_trades[open_trades["strategy"].astype(str).str.contains("مضاربة", na=False)]["market_value"].sum()
        except Exception:
            pass

        if "asset_type" in open_trades.columns and "market_value" in open_trades.columns:
            sukuk_val = open_trades[open_trades["asset_type"].astype(str).str.lower() == "sukuk"]["market_value"].sum()

        alloc_df = pd.DataFrame({
            "Asset": ["استثمار", "مضاربة", "صكوك", "كاش"],
            "Value": [invest_val, spec_val, sukuk_val, float(fin.get("cash", 0))]
        })
        alloc_df = alloc_df[alloc_df["Value"] > 0]

        c_ch1, c_ch2 = st.columns(2)
        with c_ch1:
            st.subheader("توزيع الأصول")
            if not alloc_df.empty:
                st.plotly_chart(px.pie(alloc_df, values="Value", names="Asset", hole=0.4), width="stretch")
            else:
                st.info("لا توجد أصول")
        with c_ch2:
            st.subheader("نمو المحفظة")
            crv = generate_equity_curve(df)
            if isinstance(crv, pd.DataFrame) and not crv.empty and "date" in crv.columns:
                ycol = "cumulative_invested" if "cumulative_invested" in crv.columns else crv.columns[-1]
                st.plotly_chart(px.line(crv, x="date", y=ycol), width="stretch")
            else:
                st.info("لا توجد بيانات تاريخية")
    else:
        st.info("👋 مرحباً بك! ابدأ بإضافة صفقات.")
