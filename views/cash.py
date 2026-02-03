#views/cash.py
import streamlit as st
import pandas as pd
from datetime import date

from components import render_kpi, render_custom_table, safe_fmt
from database import execute_query
from views.shared import _normalize_symbol

def view_cash_log(fin):
    st.header("💰 السيولة والسجلات المالية")

    dep = fin.get("deposits", pd.DataFrame())
    wit = fin.get("withdrawals", pd.DataFrame())
    ret = fin.get("returns", pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(dep["amount"].sum() if (not dep.empty and "amount" in dep.columns) else 0), "success", "📥")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(wit["amount"].sum() if (not wit.empty and "amount" in wit.columns) else 0), "danger", "📤")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(ret["amount"].sum() if (not ret.empty and "amount" in ret.columns) else 0), "blue", "🎁")

    st.markdown("---")
    t1, t2, t3 = st.tabs(["📥 سجل الإيداعات", "📤 سجل السحوبات", "🎁 سجل العوائد"])
    cols_base = [("date", "التاريخ", "date"), ("amount", "المبلغ", "money"), ("note", "ملاحظات", "text")]

    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("new_dep"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0, key="dep_amt")
                d = st.date_input("التاريخ", date.today(), key="dep_date")
                n = st.text_input("ملاحظة", key="dep_note")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        execute_query("INSERT INTO deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not dep.empty:
            render_custom_table(dep.sort_values("date", ascending=False) if "date" in dep.columns else dep, cols_base)
            st.markdown("---")
            with st.expander("✏️ تعديل سجل إيداع سابق"):
                if "id" in dep.columns:
                    dep_map = {f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"] for _, row in dep.iterrows()}
                    sel_dep = st.selectbox("اختر العملية للتعديل:", list(dep_map.keys()), key="edit_dep_sel")
                    if sel_dep:
                        tid = dep_map[sel_dep]
                        curr = dep[dep["id"] == tid].iloc[0]
                        with st.form(f"edit_dep_form_{tid}"):
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"dep_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"dep_fix_date_{tid}")
                            nn = st.text_input("ملاحظة", value=str(curr.get("note", "") or ""), key=f"dep_fix_note_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query("UPDATE deposits SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                                st.success("تم التعديل بنجاح")
                                st.cache_data.clear()
                                st.rerun()

    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_wit"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0, key="wit_amt")
                d = st.date_input("التاريخ", date.today(), key="wit_date")
                n = st.text_input("ملاحظة", key="wit_note")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        execute_query("INSERT INTO withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not wit.empty:
            render_custom_table(wit.sort_values("date", ascending=False) if "date" in wit.columns else wit, cols_base)
            st.markdown("---")
            with st.expander("✏️ تعديل سجل سحب سابق"):
                if "id" in wit.columns:
                    wit_map = {f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"] for _, row in wit.iterrows()}
                    sel_wit = st.selectbox("اختر العملية للتعديل:", list(wit_map.keys()), key="edit_wit_sel")
                    if sel_wit:
                        tid = wit_map[sel_wit]
                        curr = wit[wit["id"] == tid].iloc[0]
                        with st.form(f"edit_wit_form_{tid}"):
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"wit_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"wit_fix_date_{tid}")
                            nn = st.text_input("ملاحظة", value=str(curr.get("note", "") or ""), key=f"wit_fix_note_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query("UPDATE withdrawals SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                                st.success("تم التعديل بنجاح")
                                st.cache_data.clear()
                                st.rerun()

    with t3:
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("new_ret"):
                s_raw = st.text_input("رمز السهم", key="ret_sym")
                a = st.number_input("المبلغ", min_value=0.0, step=10.0, key="ret_amt")
                d = st.date_input("التاريخ", date.today(), key="ret_date")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        s = _normalize_symbol(s_raw)
                        execute_query("INSERT INTO returnsgrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not ret.empty:
            render_custom_table(
                ret.sort_values("date", ascending=False) if "date" in ret.columns else ret,
                [("date", "التاريخ", "date"), ("symbol", "السهم", "text"), ("amount", "المبلغ", "money")]
            )
