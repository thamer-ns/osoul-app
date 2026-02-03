#views/sukuk.py
import streamlit as st
import pandas as pd
from datetime import date

from components import render_kpi, render_custom_table, safe_fmt
from database import execute_query
from security import validate_trade_inputs
from views.shared import _safe_status_series

def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin.get("all_trades", pd.DataFrame())

    if df.empty or "asset_type" not in df.columns:
        sukuk = pd.DataFrame()
    else:
        sukuk = df[df["asset_type"].astype(str).str.lower() == "sukuk"].copy()

    status = _safe_status_series(sukuk) if not sukuk.empty else pd.Series([], dtype=str)
    if len(status):
        op = sukuk[status == "open"].copy()
        cl = sukuk[status.isin(["close", "closed"])].copy()
    else:
        op = sukuk.copy()
        cl = pd.DataFrame()

    t1, t2 = st.tabs(["الصكوك القائمة (Open)", "الأرشيف (Closed)"])

    with t1:
        total_cost = float(op["total_cost"].sum()) if (not op.empty and "total_cost" in op.columns) else 0
        total_market = float(op["market_value"].sum()) if (not op.empty and "market_value" in op.columns) else 0
        total_gain = float(op["gain"].sum()) if (not op.empty and "gain" in op.columns) else 0
        total_pct = (total_gain / total_cost * 100) if total_cost else 0.0

        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("إجمالي الاستثمار", safe_fmt(total_cost), "neutral", "🕌")
        with k2: render_kpi("القيمة الحالية", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")

        st.markdown("---")

        if not op.empty:
            if "company_name" not in op.columns:
                op["company_name"] = op.get("symbol", "")
            op["company_name"] = op["company_name"].fillna(op.get("symbol", ""))

            if "date" in op.columns:
                op["months_held"] = ((pd.to_datetime(date.today()) - pd.to_datetime(op["date"])).dt.days / 30).astype(int)
            else:
                op["months_held"] = 0

            if "entry_price" in op.columns:
                op["current_price"] = op["entry_price"]
            else:
                op["current_price"] = 0

            sb = st.selectbox("فرز الصكوك حسب:", ["التاريخ (الأحدث)", "القيمة (الأعلى)", "الاسم"], key="sort_sk")
            if "القيمة" in sb and "total_cost" in op.columns:
                op = op.sort_values("total_cost", ascending=False)
            elif "الاسم" in sb and "company_name" in op.columns:
                op = op.sort_values("company_name")
            else:
                if "date" in op.columns:
                    op = op.sort_values("date", ascending=False)

            render_custom_table(
                op,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("quantity", "العدد", "text"),
                    ("entry_price", "التكلفة (للوحدة)", "money"),
                    ("current_price", "السعر الحالي", "money"),
                    ("total_cost", "الاجمالي", "money"),
                    ("months_held", "المده (شهر)", "text"),
                ]
            )

            c1, c2 = st.columns(2)

            with c1:
                with st.expander("💰 بيع / تصفية صك"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        sid = st.selectbox(
                            "اختر الصك للبيع:",
                            op["id"].tolist(),
                            format_func=lambda x: f"{op[op['id']==x]['company_name'].iloc[0]}",
                            key="sell_sukuk_sel"
                        )
                        if sid:
                            curr_sell = op[op["id"] == sid].iloc[0]
                            with st.form(f"sk_sell_{sid}"):
                                st.write(f"تصفية: **{curr_sell.get('company_name','-')}**")
                                val = st.number_input("المبلغ المستلم كاملاً", min_value=0.0, step=100.0, key=f"sk_val_{sid}")
                                dt = st.date_input("تاريخ البيع", date.today(), key=f"sk_dt_{sid}")
                                if st.form_submit_button("تأكيد البيع"):
                                    qty = float(curr_sell.get("quantity", 0) or 0)
                                    if qty > 0:
                                        ep = val / qty
                                        execute_query(
                                            "UPDATE trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s",
                                            (ep, str(dt), sid)
                                        )
                                        st.success("تم الحفظ")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error("خطأ: الكمية صفر")
                    else:
                        st.info("لا توجد صكوك لاختيارها")

            with c2:
                with st.expander("✏️ تعديل بيانات صك"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        eid = st.selectbox("اختر الصك للتعديل:", op["id"].tolist(), key="sk_e")
                        if eid:
                            rw = op[op["id"] == eid].iloc[0]
                            with st.form(f"sk_edit_{eid}"):
                                nm = st.text_input("اسم الصك", value=str(rw.get("company_name", "")), key=f"sk_nm_{eid}")
                                qt = st.number_input("عدد الصكوك", value=float(rw.get("quantity", 1)), min_value=1.0, key=f"sk_qt_{eid}")
                                pr = st.number_input("قيمة الصك", value=float(rw.get("entry_price", 0)), min_value=0.0, key=f"sk_pr_{eid}")
                                try:
                                    nd_val = pd.to_datetime(rw.get("date", date.today())).date()
                                except Exception:
                                    nd_val = date.today()
                                nd = st.date_input("تاريخ الشراء", nd_val, key=f"sk_nd_{eid}")
                                if st.form_submit_button("حفظ التصحيح"):
                                    valid, msg = validate_trade_inputs(qt, pr)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET symbol=%s, company_name=%s, quantity=%s, entry_price=%s, date=%s WHERE id=%s",
                                            (nm, nm, qt, pr, str(nd), eid)
                                        )
                                        st.success("تم التعديل")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صكوك لاختيارها")
        else:
            st.info("لا توجد صكوك قائمة حالياً")

        st.markdown("---")
        if st.button("➕ إضافة صك", key="add_sukuk_btn", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with t2:
        if not cl.empty:
            if "company_name" not in cl.columns:
                cl["company_name"] = cl.get("symbol", "")
            cl["company_name"] = cl["company_name"].fillna(cl.get("symbol", ""))

            if "market_value" in cl.columns and "total_cost" in cl.columns:
                cl["realized_return"] = cl["market_value"] - cl["total_cost"]
            else:
                cl["realized_return"] = 0

            sort_by_cl = st.selectbox("فرز الأرشيف حسب:", ["تاريخ البيع (الأحدث)", "الربح (الأعلى)"], key="sort_sukuk_cl")
            if "الربح" in sort_by_cl and "realized_return" in cl.columns:
                cl = cl.sort_values("realized_return", ascending=False)
            else:
                if "exit_date" in cl.columns:
                    cl = cl.sort_values("exit_date", ascending=False)

            render_custom_table(
                cl,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("total_cost", "التكلفة", "money"),
                    ("market_value", "قيمة البيع", "money"),
                    ("realized_return", "الربح المحقق", "colorful"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )
        else:
            st.info("أرشيف الصكوك فارغ")
