"""User-scoped cash ledger UI."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi, safe_fmt
from market_data_v2 import get_ticker_symbol
from tenant_db import current_username, insert_cash_transaction, update_cash_transaction


def _save_result(ok: bool, success: str) -> None:
    if ok:
        st.success(success)
        st.cache_data.clear()
        st.rerun()
    st.error("لم تُحفظ العملية. راجع اتصال قاعدة البيانات وصلاحية السجل.")


def _edit_form(table: str, frame: pd.DataFrame, *, symbol_field: bool = False) -> None:
    if frame.empty or "id" not in frame.columns:
        return
    labels = {
        f"{row.get('date', '-')} — {row.get('amount', '-')} — {row.get('note', '')}": row["id"]
        for _, row in frame.iterrows()
    }
    selected = st.selectbox("اختر العملية", list(labels), key=f"edit_{table}_v2")
    tx_id = labels[selected]
    row = frame[frame["id"] == tx_id].iloc[0]
    try:
        default_date = pd.to_datetime(row.get("date")).date()
    except Exception:
        default_date = date.today()

    with st.form(f"edit_{table}_{tx_id}_v2"):
        amount = st.number_input(
            "المبلغ الصحيح",
            min_value=0.01,
            step=10.0,
            value=max(0.01, float(row.get("amount") or 0.01)),
        )
        tx_date = st.date_input("التاريخ الصحيح", default_date)
        note = st.text_input("ملاحظة", value=str(row.get("note") or ""))
        symbol = ""
        if symbol_field:
            symbol = st.text_input("رمز السهم", value=str(row.get("symbol") or ""))
        submitted = st.form_submit_button("حفظ التعديلات")

    if submitted:
        if symbol_field:
            symbol = get_ticker_symbol(symbol)
        _save_result(
            update_cash_transaction(
                table,
                tx_id,
                amount=amount,
                tx_date=str(tx_date),
                note=note,
                symbol=symbol,
            ),
            "تم تحديث العملية.",
        )


def view_cash_log(fin: dict) -> None:
    current_username()
    st.header("💰 السيولة والسجلات المالية")

    deposits = fin.get("deposits", pd.DataFrame())
    withdrawals = fin.get("withdrawals", pd.DataFrame())
    returns = fin.get("returns", pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi("إجمالي الإيداعات", safe_fmt(deposits["amount"].sum() if not deposits.empty else 0), "success", "📥")
    with c2:
        render_kpi("إجمالي السحوبات", safe_fmt(withdrawals["amount"].sum() if not withdrawals.empty else 0), "danger", "📤")
    with c3:
        render_kpi("التوزيعات والعوائد", safe_fmt(returns["amount"].sum() if not returns.empty else 0), "blue", "🎁")

    tab_dep, tab_wit, tab_ret = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 التوزيعات والعوائد"])
    base_columns = [("date", "التاريخ", "date"), ("amount", "المبلغ", "money"), ("note", "ملاحظات", "text")]

    with tab_dep:
        with st.expander("➕ تسجيل إيداع"):
            with st.form("new_deposit_v2"):
                amount = st.number_input("المبلغ", min_value=0.0, step=100.0)
                tx_date = st.date_input("التاريخ", date.today())
                note = st.text_input("ملاحظة")
                submitted = st.form_submit_button("حفظ")
            if submitted:
                if amount <= 0:
                    st.error("المبلغ يجب أن يكون أكبر من صفر.")
                else:
                    _save_result(insert_cash_transaction("deposits", amount=amount, tx_date=str(tx_date), note=note), "تم تسجيل الإيداع.")
        if not deposits.empty:
            render_custom_table(deposits.sort_values("date", ascending=False), base_columns)
            with st.expander("✏️ تعديل إيداع"):
                _edit_form("deposits", deposits)

    with tab_wit:
        with st.expander("➖ تسجيل سحب"):
            with st.form("new_withdrawal_v2"):
                amount = st.number_input("المبلغ", min_value=0.0, step=100.0)
                tx_date = st.date_input("التاريخ", date.today())
                note = st.text_input("ملاحظة")
                submitted = st.form_submit_button("حفظ")
            if submitted:
                if amount <= 0:
                    st.error("المبلغ يجب أن يكون أكبر من صفر.")
                else:
                    _save_result(insert_cash_transaction("withdrawals", amount=amount, tx_date=str(tx_date), note=note), "تم تسجيل السحب.")
        if not withdrawals.empty:
            render_custom_table(withdrawals.sort_values("date", ascending=False), base_columns)
            with st.expander("✏️ تعديل سحب"):
                _edit_form("withdrawals", withdrawals)

    with tab_ret:
        with st.expander("💵 تسجيل توزيع أو عائد"):
            with st.form("new_return_v2"):
                symbol = st.text_input("رمز السهم")
                amount = st.number_input("المبلغ", min_value=0.0, step=10.0)
                tx_date = st.date_input("التاريخ", date.today())
                note = st.text_input("ملاحظة")
                submitted = st.form_submit_button("حفظ")
            if submitted:
                if amount <= 0:
                    st.error("المبلغ يجب أن يكون أكبر من صفر.")
                else:
                    _save_result(
                        insert_cash_transaction("returnsgrants", amount=amount, tx_date=str(tx_date), note=note, symbol=get_ticker_symbol(symbol)),
                        "تم تسجيل التوزيع أو العائد.",
                    )
        if not returns.empty:
            render_custom_table(
                returns.sort_values("date", ascending=False),
                [("date", "التاريخ", "date"), ("symbol", "السهم", "text"), ("amount", "المبلغ", "money"), ("note", "ملاحظات", "text")],
            )
            with st.expander("✏️ تعديل توزيع أو عائد"):
                _edit_form("returnsgrants", returns, symbol_field=True)
