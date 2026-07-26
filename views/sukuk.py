from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi, safe_fmt
from database import execute_query
from security import validate_trade_inputs
from views.shared import _safe_status_series


def _save(query: str, params: tuple, message: str) -> bool:
    if execute_query(query, params):
        st.success(message)
        st.cache_data.clear()
        return True
    st.error("تعذر حفظ العملية في قاعدة البيانات. لم تتغير البيانات.")
    return False


def _safe_date(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.date() if pd.notna(parsed) else date.today()


def view_sukuk_portfolio(fin):
    fin = fin or {}
    st.header("📜 محفظة الصكوك")
    trades = fin.get("all_trades", pd.DataFrame())
    if trades.empty or "asset_type" not in trades.columns:
        sukuk = pd.DataFrame()
    else:
        sukuk = trades[
            trades["asset_type"].astype(str).str.lower().eq("sukuk")
        ].copy()

    status = (
        _safe_status_series(sukuk)
        if not sukuk.empty
        else pd.Series(dtype=str)
    )
    open_sukuk = (
        sukuk[status == "open"].copy()
        if len(status)
        else pd.DataFrame()
    )
    closed_sukuk = (
        sukuk[status.isin(["close", "closed"])].copy()
        if len(status)
        else pd.DataFrame()
    )

    open_tab, archive_tab = st.tabs(["الصكوك القائمة", "الأرشيف"])
    with open_tab:
        total_cost = (
            float(open_sukuk["total_cost"].sum())
            if not open_sukuk.empty and "total_cost" in open_sukuk.columns
            else 0.0
        )
        total_value = (
            float(open_sukuk["market_value"].sum())
            if not open_sukuk.empty and "market_value" in open_sukuk.columns
            else total_cost
        )
        total_gain = total_value - total_cost
        total_return = total_gain / total_cost * 100 if total_cost else 0.0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi("إجمالي الاستثمار", safe_fmt(total_cost), "neutral", "🕌")
        with c2:
            render_kpi("القيمة المسجلة", safe_fmt(total_value), "blue", "📊")
        with c3:
            render_kpi(
                "الربح والخسارة",
                safe_fmt(total_gain),
                "success" if total_gain >= 0 else "danger",
                "📈",
            )
        with c4:
            render_kpi(
                "العائد",
                f"{total_return:.2f}%",
                "success" if total_return >= 0 else "danger",
                "٪",
            )

        st.caption(
            "القيمة الحالية للصك تساوي التكلفة المسجلة ما لم تُدخل قيمة تصفية فعلية؛ "
            "التوزيعات الدورية تُسجل من صفحة السيولة."
        )

        if open_sukuk.empty:
            st.info("لا توجد صكوك قائمة حاليًا")
        else:
            frame = open_sukuk.copy()
            if "company_name" not in frame.columns:
                frame["company_name"] = frame.get("symbol", "")
            frame["company_name"] = frame["company_name"].fillna(
                frame.get("symbol", "")
            )
            frame["current_price"] = pd.to_numeric(
                frame.get("entry_price", 0.0),
                errors="coerce",
            ).fillna(0.0)
            if "date" in frame.columns:
                bought = pd.to_datetime(frame["date"], errors="coerce")
                frame["months_held"] = (
                    (pd.Timestamp(date.today()) - bought).dt.days.div(30)
                ).fillna(0).clip(lower=0).astype(int)
            else:
                frame["months_held"] = 0

            sort_by = st.selectbox(
                "فرز الصكوك حسب",
                ["التاريخ الأحدث", "القيمة الأعلى", "الاسم"],
            )
            if sort_by == "القيمة الأعلى" and "total_cost" in frame.columns:
                frame = frame.sort_values("total_cost", ascending=False)
            elif sort_by == "الاسم":
                frame = frame.sort_values("company_name")
            elif "date" in frame.columns:
                frame = frame.sort_values("date", ascending=False)

            render_custom_table(
                frame,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("quantity", "العدد", "number"),
                    ("entry_price", "تكلفة الوحدة", "money"),
                    ("total_cost", "الإجمالي", "money"),
                    ("months_held", "مدة الاحتفاظ بالشهور", "number"),
                ],
            )

            left, right = st.columns(2)
            with left:
                with st.expander("💰 تصفية صك"):
                    options = {
                        f"{row.get('company_name') or row.get('symbol')} — {safe_fmt(row.get('total_cost', 0))}": row["id"]
                        for _, row in frame.iterrows()
                        if pd.notna(row.get("id"))
                    }
                    selected = st.selectbox(
                        "اختر الصك",
                        list(options),
                        key="sell_sukuk_selection",
                    )
                    row = frame[frame["id"] == options[selected]].iloc[0]
                    with st.form(f"sell_sukuk_{int(row['id'])}"):
                        received = st.number_input(
                            "إجمالي المبلغ المستلم",
                            min_value=0.01,
                            value=max(
                                0.01,
                                float(row.get("total_cost", 0) or 0),
                            ),
                            step=100.0,
                        )
                        sold_at = st.date_input(
                            "تاريخ التصفية",
                            date.today(),
                        )
                        submitted = st.form_submit_button("تأكيد التصفية")
                    if submitted:
                        quantity = float(row.get("quantity", 0) or 0)
                        if quantity <= 0:
                            st.error("عدد الوحدات غير صالح")
                        else:
                            exit_price = received / quantity
                            valid, message = validate_trade_inputs(
                                quantity,
                                exit_price,
                            )
                            if not valid:
                                st.error(message)
                            elif _save(
                                "UPDATE trades SET status='Close', "
                                "exit_price=%s, exit_date=%s, "
                                "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                                (
                                    exit_price,
                                    str(sold_at),
                                    int(row["id"]),
                                ),
                                "تم تسجيل تصفية الصك",
                            ):
                                st.rerun()

            with right:
                with st.expander("✏️ تعديل بيانات صك"):
                    edit_options = {
                        f"{row.get('company_name') or row.get('symbol')} — ID:{int(row['id'])}": row["id"]
                        for _, row in frame.iterrows()
                        if pd.notna(row.get("id"))
                    }
                    selected = st.selectbox(
                        "اختر الصك",
                        list(edit_options),
                        key="edit_sukuk_selection",
                    )
                    row = frame[
                        frame["id"] == edit_options[selected]
                    ].iloc[0]
                    with st.form(f"edit_sukuk_{int(row['id'])}"):
                        name = st.text_input(
                            "اسم الصك",
                            value=str(row.get("company_name", "") or ""),
                        )
                        quantity = st.number_input(
                            "عدد الصكوك",
                            min_value=0.001,
                            value=max(
                                0.001,
                                float(row.get("quantity", 1) or 1),
                            ),
                            step=1.0,
                        )
                        unit_cost = st.number_input(
                            "قيمة الوحدة",
                            min_value=0.01,
                            value=max(
                                0.01,
                                float(row.get("entry_price", 0) or 0),
                            ),
                            step=10.0,
                        )
                        bought_at = st.date_input(
                            "تاريخ الشراء",
                            _safe_date(row.get("date")),
                        )
                        submitted = st.form_submit_button("حفظ التصحيح")
                    if submitted:
                        valid, message = validate_trade_inputs(
                            quantity,
                            unit_cost,
                        )
                        if not valid:
                            st.error(message)
                        elif not name.strip():
                            st.error("أدخل اسم الصك")
                        elif _save(
                            "UPDATE trades SET company_name=%s, "
                            "quantity=%s, entry_price=%s, date=%s, "
                            "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                            (
                                name.strip(),
                                quantity,
                                unit_cost,
                                str(bought_at),
                                int(row["id"]),
                            ),
                            "تم تعديل بيانات الصك",
                        ):
                            st.rerun()

        if st.button("➕ إضافة صك", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with archive_tab:
        if closed_sukuk.empty:
            st.info("أرشيف الصكوك فارغ")
        else:
            frame = closed_sukuk.copy()
            for column in ("quantity", "entry_price", "exit_price"):
                if column not in frame.columns:
                    frame[column] = 0.0
                frame[column] = pd.to_numeric(
                    frame[column],
                    errors="coerce",
                ).fillna(0.0)
            frame["total_cost"] = frame["quantity"] * frame["entry_price"]
            frame["sale_value"] = frame["quantity"] * frame["exit_price"]
            frame["realized_return"] = (
                frame["sale_value"] - frame["total_cost"]
            )
            frame["realized_return_pct"] = (
                frame["realized_return"]
                .div(frame["total_cost"].replace(0, pd.NA))
                .mul(100)
                .fillna(0.0)
            )
            if "exit_date" in frame.columns:
                frame = frame.sort_values("exit_date", ascending=False)
            render_custom_table(
                frame,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("total_cost", "التكلفة", "money"),
                    ("sale_value", "قيمة التصفية", "money"),
                    ("realized_return", "الربح المحقق", "colorful"),
                    ("realized_return_pct", "العائد", "percent"),
                    ("exit_date", "تاريخ التصفية", "date"),
                ],
            )
