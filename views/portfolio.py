#views/portfolio.py
import streamlit as st
import pandas as pd
from datetime import date

from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from database import execute_query, fetch_table
from market_data import fetch_batch_data
from data_source import get_company_details
from security import validate_trade_inputs
from views.shared import _safe_status_series, _clean_symbols_list, _normalize_symbol

def view_portfolio(fin, key):
    ts = "مضاربة" if key == "spec" else "استثمار"
    st.header(f"💼 محفظة {ts}")

    st.markdown(
        """<style>
        .finance-table td, .finance-table th {
            white-space: nowrap !important;
            font-size: 0.85rem !important;
            vertical-align: middle !important;
        }
        </style>""",
        unsafe_allow_html=True
    )

    df = fin.get("all_trades", pd.DataFrame())
    if df.empty:
        sub = pd.DataFrame(columns=["status", "total_cost", "market_value", "gain", "symbol", "date", "id"])
    else:
        if "strategy" in df.columns:
            sub = df[df["strategy"].astype(str).str.contains(ts, na=False)].copy()
        else:
            sub = df.copy()

    status = _safe_status_series(sub) if not sub.empty else pd.Series([], dtype=str)
    if len(status):
        op = sub[status == "open"].copy()
        cl = sub[status.isin(["close", "closed"])].copy()
    else:
        op = sub.copy()
        cl = pd.DataFrame()

    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])

    with t1:
        k1, k2, k3, k4 = st.columns(4)
        total_cost = float(op["total_cost"].sum()) if (not op.empty and "total_cost" in op.columns) else 0
        total_market = float(op["market_value"].sum()) if (not op.empty and "market_value" in op.columns) else 0
        total_gain = float(op["gain"].sum()) if (not op.empty and "gain" in op.columns) else 0
        total_pct = (total_gain / total_cost * 100) if total_cost else 0.0

        with k1: render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral")
        with k2: render_kpi("سعر السوق", safe_fmt(total_market), "blue")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")

        st.markdown("---")

        if not op.empty:
            for col in ["company_name", "sector", "gain_pct", "weight"]:
                if col not in op.columns:
                    op[col] = ""

            sort_opts = [
                "الربح (الأعلى)", "القيمة (الأعلى)", "التاريخ (الأحدث)", "الرمز", "الشركة", "القطاع",
                "الكمية", "التكلفة", "السعر الحالي", "نسبة الربح", "التغير اليومي"
            ]
            c_sort, _ = st.columns([1, 3])
            sort_by = c_sort.selectbox(f"فرز {ts} حسب:", sort_opts, key=f"s_op_{key}")

            symbols = _clean_symbols_list(op["symbol"].astype(str).tolist()) if "symbol" in op.columns else []
            try:
                live_data = fetch_batch_data(symbols) if symbols else {}
            except Exception:
                live_data = {}

            if "symbol" in op.columns:
                op["symbol"] = op["symbol"].astype(str).apply(_normalize_symbol)

            op["current_price"] = op["symbol"].apply(lambda x: live_data.get(x, {}).get("price", 0))
            op["prev_close"] = op["symbol"].apply(lambda x: live_data.get(x, {}).get("prev_close", 0))

            op["day_change"] = op.apply(
                lambda r: ((r.get("current_price", 0) - r.get("prev_close", 0)) / r.get("prev_close", 1) * 100)
                if (r.get("prev_close", 0) and r.get("prev_close", 0) > 0) else 0,
                axis=1
            )
            op["status_ar"] = "مفتوحة"

            if "الربح" in sort_by and "gain" in op.columns:
                op = op.sort_values("gain", ascending=False)
            elif "القيمة" in sort_by and "market_value" in op.columns:
                op = op.sort_values("market_value", ascending=False)
            elif "الرمز" in sort_by and "symbol" in op.columns:
                op = op.sort_values("symbol")
            elif "التغير اليومي" in sort_by and "day_change" in op.columns:
                op = op.sort_values("day_change", ascending=False)
            elif "نسبة الربح" in sort_by and "gain_pct" in op.columns:
                op = op.sort_values("gain_pct", ascending=False)
            elif "الشركة" in sort_by and "company_name" in op.columns:
                op = op.sort_values("company_name")
            elif "القطاع" in sort_by and "sector" in op.columns:
                op = op.sort_values("sector")
            elif "التكلفة" in sort_by and "total_cost" in op.columns:
                op = op.sort_values("total_cost", ascending=False)
            else:
                if "date" in op.columns:
                    op = op.sort_values("date", ascending=False)

            render_custom_table(
                op,
                [
                    ("company_name", "اسم الشركة", "text"),
                    ("sector", "القطاع", "text"),
                    ("status_ar", "الحالة", "badge"),
                    ("symbol", "رمز الشركة", "text"),
                    ("date", "تاريخ الشراء", "date"),
                    ("quantity", "الكمية", "money"),
                    ("entry_price", "سعر الشراء", "money"),
                    ("total_cost", "التكلفة", "money"),
                    ("current_price", "السعر الحالي", "money"),
                    ("market_value", "سعر السوق", "money"),
                    ("gain", "الربح والخسارة", "colorful"),
                    ("gain_pct", "نسبة الربح والخسارة", "percent"),
                    ("weight", "وزن السهم", "percent"),
                    ("day_change", "نسبة التغير اليومي", "percent"),
                ]
            )

            c_a1, c_a2 = st.columns(2)

            with c_a1:
                with st.expander("🔴 تسجيل بيع / إغلاق"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        s_id = st.selectbox(
                            "اختر الصفقة",
                            op["id"].tolist(),
                            format_func=lambda x: f"{op[op['id']==x]['company_name'].iloc[0]} ({op[op['id']==x]['symbol'].iloc[0]})",
                            key=f"sell_{key}"
                        )
                        if s_id:
                            with st.form(f"frm_sell_{key}_{s_id}"):
                                pr = st.number_input("سعر البيع", min_value=0.0, step=0.01, key=f"sell_price_{key}_{s_id}")
                                dt = st.date_input("تاريخ البيع", date.today(), key=f"sell_date_{key}_{s_id}")
                                if st.form_submit_button("تأكيد"):
                                    valid, msg = validate_trade_inputs(1, pr)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s",
                                            (pr, str(dt), s_id)
                                        )
                                        st.success("تم البيع")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صفقات لاختيارها")

            with c_a2:
                with st.expander("✏️ تعديل صفقة (تصحيح خطأ)"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        e_id = st.selectbox("اختر الصفقة", op["id"].tolist(), key=f"edit_{key}")
                        if e_id:
                            rw = op[op["id"] == e_id].iloc[0]
                            with st.form(f"frm_edit_{key}_{e_id}"):
                                nq = st.number_input("الكمية", value=float(rw.get("quantity", 1)), min_value=1.0, key=f"edit_q_{key}_{e_id}")
                                np_ = st.number_input("سعر الشراء", value=float(rw.get("entry_price", 0)), min_value=0.0, key=f"edit_p_{key}_{e_id}")
                                try:
                                    nd_val = pd.to_datetime(rw.get("date", date.today())).date()
                                except Exception:
                                    nd_val = date.today()
                                nd = st.date_input("تاريخ الشراء", nd_val, key=f"edit_d_{key}_{e_id}")
                                if st.form_submit_button("حفظ"):
                                    valid, msg = validate_trade_inputs(nq, np_)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET quantity=%s, entry_price=%s, date=%s WHERE id=%s",
                                            (nq, np_, str(nd), e_id)
                                        )
                                        st.success("تم التعديل")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صفقات لاختيارها")
        else:
            st.info("لا توجد صفقات قائمة حالياً")

        st.markdown("---")
        if st.button("➕ إضافة سهم", key=f"add_{key}", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with t2:
        if not cl.empty:
            sort_cl = st.selectbox(
                "فرز الأرشيف:",
                ["التاريخ (الأحدث)", "الربح (الأعلى)", "قيمة البيع (الأعلى)"],
                key=f"s_cl_{key}"
            )
            if "الربح" in sort_cl and "gain" in cl.columns:
                cl = cl.sort_values("gain", ascending=False)
            elif "قيمة البيع" in sort_cl and "market_value" in cl.columns:
                cl = cl.sort_values("market_value", ascending=False)
            else:
                if "exit_date" in cl.columns:
                    cl = cl.sort_values("exit_date", ascending=False)

            render_custom_table(
                cl,
                [
                    ("company_name", "الشركة", "text"),
                    ("symbol", "الرمز", "text"),
                    ("gain", "الربح", "colorful"),
                    ("gain_pct", "%", "percent"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )
        else:
            st.info("الأرشيف فارغ")

def render_pulse_dashboard():
    st.header("نبض السوق")
    try:
        trades = fetch_table("trades")
    except Exception:
        trades = pd.DataFrame()

    syms = list(trades["symbol"].astype(str).unique()) if (not trades.empty and "symbol" in trades.columns) else []
    syms = _clean_symbols_list(syms)
    if syms:
        d = fetch_batch_data(syms)
        cols = st.columns(4)
        for i, (s, v) in enumerate(d.items()):
            prev = v.get("prev_close") or 0
            chg = ((v.get("price", 0) - prev) / prev) * 100 if prev else 0
            with cols[i % 4]:
                render_ticker_card(s, "سهم", v.get("price", 0), chg)
    else:
        st.info("لا توجد رموز لعرض نبض السوق.")

def view_add_trade():
    st.header("➕ إضافة صفقة")
    with st.form("add_t"):
        c1, c2 = st.columns(2)
        s_raw = c1.text_input("رمز السهم (مثال: 1120)", key="add_sym")
        typ = c2.selectbox("نوع الصفقة", ["استثمار", "مضاربة", "صكوك"], key="add_typ")
        c3, c4, c5 = st.columns(3)
        q = c3.number_input("الكمية", min_value=1.0, key="add_q")
        p = c4.number_input("السعر", min_value=0.0, key="add_p")
        d = c5.date_input("التاريخ", date.today(), key="add_d")

        if st.form_submit_button("حفظ"):
            valid, msg = validate_trade_inputs(q, p)
            if valid:
                s = _normalize_symbol(s_raw)

                try:
                    info = get_company_details(s)
                    if isinstance(info, (list, tuple)) and len(info) >= 2:
                        nm, sec = info[0], info[1]
                    elif isinstance(info, dict):
                        nm = info.get("name") or info.get("Name") or s
                        sec = info.get("sector") or info.get("Sector") or ""
                    else:
                        nm, sec = s, ""
                except Exception:
                    nm, sec = s, ""

                at = "Sukuk" if typ == "صكوك" else "Stock"
                execute_query(
                    "INSERT INTO trades (symbol, company_name, sector, asset_type, quantity, entry_price, strategy, status, date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'Open',%s)",
                    (s, nm, sec, at, q, p, typ, str(d))
                )
                st.success("تم")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)
