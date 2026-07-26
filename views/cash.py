from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi, safe_fmt
from database import execute_query
from views.shared import _normalize_symbol


def _amount(value) -> float:
    try:
        return max(0.0, float(value))
    except Exception:
        return 0.0


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


def _render_edit_form(frame: pd.DataFrame, table: str, key: str) -> None:
    if frame.empty or "id" not in frame.columns:
        return
    mapping = {
        f"{row.get('date', '-')} — {safe_fmt(row.get('amount', 0))} — {row.get('note', '')}": row["id"]
        for _, row in frame.iterrows()
    }
    selected = st.selectbox(
        "اختر العملية",
        list(mapping),
        key=f"edit_{key}_selection",
    )
    row = frame[frame["id"] == mapping[selected]].iloc[0]
    with st.form(f"edit_{key}_{int(row['id'])}"):
        amount = st.number_input(
            "المبلغ الصحيح",
            min_value=0.01,
            value=max(0.01, _amount(row.get("amount"))),
            step=10.0,
        )
        occurred_at = st.date_input(
            "التاريخ الصحيح",
            _safe_date(row.get("date")),
        )
        note = st.text_input(
            "ملاحظة",
            value=str(row.get("note", "") or ""),
        )
        submitted = st.form_submit_button("حفظ التعديلات")
    if submitted and _save(
        f"UPDATE {table} SET amount=%s, date=%s, note=%s WHERE id=%s",
        (amount, str(occurred_at), note.strip(), int(row["id"])),
        "تم تعديل العملية",
    ):
        st.rerun()


def view_cash_log(fin):
    fin = fin or {}
    st.header("💰 السيولة والسجلات المالية")
    deposits = fin.get("deposits", pd.DataFrame())
    withdrawals = fin.get("withdrawals", pd.DataFrame())
    returns = fin.get("returns", pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi(
            "إجمالي الإيداعات",
            safe_fmt(
                deposits["amount"].sum()
                if not deposits.empty and "amount" in deposits.columns
                else 0
            ),
            "success",
            "📥",
        )
    with c2:
        render_kpi(
            "إجمالي السحوبات",
            safe_fmt(
                withdrawals["amount"].sum()
                if not withdrawals.empty and "amount" in withdrawals.columns
                else 0
            ),
            "danger",
            "📤",
        )
    with c3:
        render_kpi(
            "إجمالي التوزيعات والعوائد",
            safe_fmt(
                returns["amount"].sum()
                if not returns.empty and "amount" in returns.columns
                else 0
            ),
            "blue",
            "🎁",
        )

    deposit_tab, withdrawal_tab, return_tab = st.tabs(
        ["📥 الإيداعات", "📤 السحوبات", "🎁 التوزيعات والعوائد"]
    )
    base_columns = [
        ("date", "التاريخ", "date"),
        ("amount", "المبلغ", "money"),
        ("note", "ملاحظات", "text"),
    ]

    with deposit_tab:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("new_deposit"):
                amount = st.number_input(
                    "المبلغ",
                    min_value=0.01,
                    step=100.0,
                )
                occurred_at = st.date_input("التاريخ", date.today())
                note = st.text_input("ملاحظة")
                submitted = st.form_submit_button("حفظ")
            if submitted and _save(
                "INSERT INTO deposits (date, amount, note) VALUES (%s,%s,%s)",
                (str(occurred_at), amount, note.strip()),
                "تم تسجيل الإيداع",
            ):
                st.rerun()
        if not deposits.empty:
            ordered = (
                deposits.sort_values("date", ascending=False)
                if "date" in deposits.columns
                else deposits
            )
            render_custom_table(ordered, base_columns)
            with st.expander("✏️ تعديل إيداع سابق"):
                _render_edit_form(deposits, "deposits", "deposit")

    with withdrawal_tab:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_withdrawal"):
                amount = st.number_input(
                    "المبلغ",
                    min_value=0.01,
                    step=100.0,
                )
                occurred_at = st.date_input("التاريخ", date.today())
                note = st.text_input("ملاحظة")
                submitted = st.form_submit_button("حفظ")
            if submitted and _save(
                "INSERT INTO withdrawals (date, amount, note) VALUES (%s,%s,%s)",
                (str(occurred_at), amount, note.strip()),
                "تم تسجيل السحب",
            ):
                st.rerun()
        if not withdrawals.empty:
            ordered = (
                withdrawals.sort_values("date", ascending=False)
                if "date" in withdrawals.columns
                else withdrawals
            )
            render_custom_table(ordered, base_columns)
            with st.expander("✏️ تعديل سحب سابق"):
                _render_edit_form(
                    withdrawals,
                    "withdrawals",
                    "withdrawal",
                )

    with return_tab:
        st.caption(
            "التوزيع المسجل هنا يُضاف إلى كاش المحفظة ويُعامل كعائد داخلي. "
            "إذا أخرجته من المحفظة فسجل سحبًا منفصلًا."
        )
        with st.expander("💵 تسجيل توزيع أو عائد"):
            with st.form("new_return"):
                raw_symbol = st.text_input("رمز السهم")
                amount = st.number_input(
                    "المبلغ",
                    min_value=0.01,
                    step=10.0,
                )
                occurred_at = st.date_input("التاريخ", date.today())
                submitted = st.form_submit_button("حفظ")
            if submitted:
                symbol = _normalize_symbol(raw_symbol)
                if not symbol:
                    st.error("أدخل رمز سهم صحيحًا")
                elif _save(
                    "INSERT INTO returnsgrants "
                    "(date, symbol, amount) VALUES (%s,%s,%s)",
                    (str(occurred_at), symbol, amount),
                    "تم تسجيل العائد",
                ):
                    st.rerun()
        if not returns.empty:
            ordered = (
                returns.sort_values("date", ascending=False)
                if "date" in returns.columns
                else returns
            )
            render_custom_table(
                ordered,
                [
                    ("date", "التاريخ", "date"),
                    ("symbol", "السهم", "text"),
                    ("amount", "المبلغ", "money"),
                ],
            )
