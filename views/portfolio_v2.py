"""User-scoped portfolio UI for Osoli v2."""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi, render_ticker_card, safe_fmt
from data_source import get_company_details
from market_data_v2 import fetch_batch_data, get_ticker_symbol
from security_v2 import validate_trade_inputs
from tenant_db import close_trade, current_username, insert_trade, update_trade

try:
    from ai_engine_core.portfolio import (
        calculate_portfolio_risk_score,
        generate_rebalancing_suggestions,
        portfolio_risk_gates,
        run_stress_test,
    )
except Exception:  # pragma: no cover
    calculate_portfolio_risk_score = None
    generate_rebalancing_suggestions = None
    portfolio_risk_gates = None
    run_stress_test = None


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _status_series(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty or "status" not in frame.columns:
        return pd.Series([], dtype=str)
    return frame["status"].astype(str).str.strip().str.lower()


def _refresh(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy(), {}
    out = frame.copy()
    for column in (
        "quantity", "entry_price", "current_price", "entry_fees", "exit_fees",
        "total_cost", "market_value", "gain", "gain_pct",
    ):
        if column not in out.columns:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)

    symbols = [str(x).strip() for x in out.get("symbol", pd.Series(dtype=str)).dropna().unique() if str(x).strip()]
    quotes = fetch_batch_data(symbols)
    for idx, row in out.iterrows():
        symbol = str(row.get("symbol") or "").strip()
        norm = get_ticker_symbol(symbol)
        quote = quotes.get(symbol.upper()) or quotes.get(norm.upper()) or {}
        price = _num(quote.get("price"), 0.0)
        if price <= 0:
            price = _num(row.get("current_price"), _num(row.get("entry_price")))
        out.at[idx, "current_price"] = price
        out.at[idx, "prev_close"] = quote.get("prev_close")
        out.at[idx, "price_source"] = quote.get("source", "غير متاح")

    out["total_cost"] = out["quantity"] * out["entry_price"] + out["entry_fees"]
    out["market_value"] = out["quantity"] * out["current_price"]
    out["gain"] = out["market_value"] - out["total_cost"]
    out["gain_pct"] = out["gain"].div(out["total_cost"].replace(0, pd.NA)).mul(100).fillna(0.0)
    out["day_change"] = 0.0
    has_prev = pd.to_numeric(out["prev_close"], errors="coerce").fillna(0.0) > 0
    out.loc[has_prev, "day_change"] = (
        (out.loc[has_prev, "current_price"] - pd.to_numeric(out.loc[has_prev, "prev_close"]))
        / pd.to_numeric(out.loc[has_prev, "prev_close"]) * 100.0
    )
    return out, quotes


def _clear_and_rerun() -> None:
    st.cache_data.clear()
    st.rerun()


def _trade_label(row: pd.Series) -> str:
    company = row.get("company_name") or row.get("name") or row.get("stock_name") or row.get("company") or "بدون اسم"
    status = "مغلقة" if str(row.get("status", "")).lower() in {"close", "closed"} else "مفتوحة"
    return f"[{status}] {company} ({row.get('symbol', '')}) — #{row.get('id', '')}"


def _render_risk_panel(fin: dict, open_positions: pd.DataFrame) -> None:
    market_value = float(open_positions["market_value"].sum()) if not open_positions.empty else 0.0
    cash = _num(fin.get("cash"))
    portfolio_value = _num(fin.get("portfolio_value"), cash + market_value)
    cash_pct = _num(fin.get("cash_pct"), (cash / portfolio_value * 100.0) if portfolio_value > 0 else 0.0)

    with st.expander("🛡️ إدارة مخاطر المحفظة", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi("قيمة المحفظة", safe_fmt(portfolio_value), "blue")
        with c2:
            render_kpi("السيولة", safe_fmt(cash), "neutral")
        with c3:
            render_kpi("نسبة السيولة", f"{cash_pct:.1f}%", "success" if cash_pct >= 15 else "danger")
        risk_score = None
        if callable(calculate_portfolio_risk_score) and not open_positions.empty:
            try:
                risk_score = float(calculate_portfolio_risk_score(open_positions, cash_pct))
            except Exception:
                risk_score = None
        with c4:
            render_kpi("درجة المخاطر", "غير متاح" if risk_score is None else f"{risk_score:.0f}/100", "neutral" if risk_score is None else ("danger" if risk_score >= 70 else "success"))

        gates = {"pass": True, "reasons": []}
        if callable(portfolio_risk_gates) and not open_positions.empty:
            try:
                gates = portfolio_risk_gates(open_positions, cash_pct) or gates
            except Exception:
                pass
        if gates.get("pass", True):
            st.success("بوابات المخاطر ناجحة.")
        else:
            st.warning("توجد ملاحظات تستدعي تخفيف المخاطر.")
            for reason in (gates.get("reasons") or [])[:8]:
                st.write(f"- {reason}")

        if callable(run_stress_test):
            try:
                stress = run_stress_test(portfolio_value, open_positions) or {}
            except Exception:
                stress = {}
            scenarios = stress.get("scenarios") or []
            if scenarios:
                frame = pd.DataFrame(scenarios)
                columns = []
                for key, label, kind in (("scenario", "السيناريو", "text"), ("impact_pct", "الأثر %", "percent"), ("impact_value", "الأثر بالقيمة", "money"), ("note", "ملاحظة", "text")):
                    if key in frame.columns:
                        columns.append((key, label, kind))
                render_custom_table(frame, columns)

        suggestions = []
        if callable(generate_rebalancing_suggestions):
            try:
                suggestions = generate_rebalancing_suggestions(open_positions, cash_pct) or []
            except Exception:
                suggestions = []
        if suggestions:
            st.markdown("**اقتراحات إعادة التوازن**")
            for level, text in suggestions[:8]:
                if "danger" in str(level).lower():
                    st.error(text)
                elif "warn" in str(level).lower() or "priority" in str(level).lower():
                    st.warning(text)
                else:
                    st.info(text)


def view_portfolio(fin: dict, key: str) -> None:
    current_username()
    strategy_ar = {"spec": "مضاربة", "invest": "استثمار", "sukuk": "صكوك"}.get(key, "استثمار")
    st.header(f"💼 محفظة {strategy_ar}")

    all_trades = fin.get("all_trades", pd.DataFrame()) if isinstance(fin, dict) else pd.DataFrame()
    if key == "sukuk" and not all_trades.empty and "asset_type" in all_trades.columns:
        trades = all_trades[all_trades["asset_type"].astype(str).str.lower().eq("sukuk")].copy()
    elif not all_trades.empty and "strategy" in all_trades.columns:
        trades = all_trades[all_trades["strategy"].astype(str).str.contains(strategy_ar, na=False)].copy()
    else:
        trades = all_trades.copy()

    status = _status_series(trades)
    open_positions = trades[status.eq("open")].copy() if len(status) else pd.DataFrame()
    closed_positions = trades[status.isin(["close", "closed"])].copy() if len(status) else pd.DataFrame()
    open_positions, _ = _refresh(open_positions)

    tab_open, tab_archive = st.tabs(["الصفقات القائمة", "الأرشيف"])

    with tab_open:
        total_cost = float(open_positions["total_cost"].sum()) if not open_positions.empty else 0.0
        total_market = float(open_positions["market_value"].sum()) if not open_positions.empty else 0.0
        total_gain = float(open_positions["gain"].sum()) if not open_positions.empty else 0.0
        total_pct = total_gain / total_cost * 100.0 if total_cost else 0.0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral")
        with c2:
            render_kpi("القيمة السوقية", safe_fmt(total_market), "blue")
        with c3:
            render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger")
        with c4:
            render_kpi("العائد", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger")

        _render_risk_panel(fin or {}, open_positions)

        if not open_positions.empty:
            open_positions["status_ar"] = "مفتوحة"
            render_custom_table(
                open_positions,
                [
                    ("company_name", "الشركة", "text"), ("sector", "القطاع", "text"), ("status_ar", "الحالة", "badge"),
                    ("symbol", "الرمز", "text"), ("date", "تاريخ الشراء", "date"), ("quantity", "الكمية", "number"),
                    ("entry_price", "سعر الشراء", "money"), ("entry_fees", "رسوم الدخول", "money"), ("total_cost", "إجمالي التكلفة", "money"),
                    ("current_price", "السعر الحالي", "money"), ("market_value", "القيمة السوقية", "money"), ("gain", "الربح/الخسارة", "colorful"),
                    ("gain_pct", "العائد %", "percent"), ("day_change", "التغير اليومي", "percent"), ("price_source", "المصدر", "text"),
                ],
            )
        else:
            st.info("لا توجد صفقات قائمة حاليًا.")

        left, right = st.columns(2)
        with left:
            with st.expander("🔴 إغلاق صفقة"):
                if open_positions.empty or "id" not in open_positions.columns:
                    st.info("لا توجد صفقة قابلة للإغلاق.")
                else:
                    options = {_trade_label(row): row["id"] for _, row in open_positions.iterrows()}
                    selected = st.selectbox("اختر الصفقة", list(options), key=f"close_{key}")
                    trade_id = options[selected]
                    with st.form(f"close_trade_{key}_{trade_id}"):
                        exit_price = st.number_input("سعر البيع", min_value=0.0, step=0.01)
                        exit_fees = st.number_input("رسوم البيع", min_value=0.0, step=0.01)
                        exit_date = st.date_input("تاريخ البيع", date.today())
                        submitted = st.form_submit_button("تأكيد الإغلاق")
                    if submitted:
                        valid, message = validate_trade_inputs(1, exit_price)
                        if not valid:
                            st.error(message)
                        elif close_trade(trade_id, exit_price=exit_price, exit_date=str(exit_date), exit_fees=exit_fees):
                            st.success("تم إغلاق الصفقة.")
                            _clear_and_rerun()
                        else:
                            st.error("فشل إغلاق الصفقة ولم تُحفظ التغييرات.")

        with right:
            with st.expander("✏️ تعديل صفقة مفتوحة أو مغلقة"):
                editable = pd.concat([open_positions, closed_positions], ignore_index=True)
                if editable.empty or "id" not in editable.columns:
                    st.info("لا توجد صفقات قابلة للتعديل.")
                else:
                    editable = editable.drop_duplicates(subset=["id"])
                    options = {_trade_label(row): row["id"] for _, row in editable.iterrows()}
                    selected = st.selectbox("اختر الصفقة", list(options), key=f"edit_{key}")
                    trade_id = options[selected]
                    row = editable[editable["id"] == trade_id].iloc[0]
                    is_closed = str(row.get("status", "")).lower() in {"close", "closed"}
                    try:
                        default_date = pd.to_datetime(row.get("date")).date()
                    except Exception:
                        default_date = date.today()
                    with st.form(f"edit_trade_{key}_{trade_id}"):
                        quantity = st.number_input("الكمية", min_value=0.001, step=0.001, value=max(0.001, _num(row.get("quantity"), 1.0)))
                        entry_price = st.number_input("سعر الشراء", min_value=0.0, step=0.01, value=_num(row.get("entry_price")))
                        entry_fees = st.number_input("رسوم الدخول", min_value=0.0, step=0.01, value=_num(row.get("entry_fees")))
                        trade_date = st.date_input("تاريخ الشراء", default_date)
                        notes = st.text_area("ملاحظات", value=str(row.get("notes") or ""))
                        exit_price = None
                        exit_date = None
                        exit_fees = 0.0
                        if is_closed:
                            exit_price = st.number_input("سعر البيع", min_value=0.0, step=0.01, value=_num(row.get("exit_price")))
                            exit_fees = st.number_input("رسوم البيع", min_value=0.0, step=0.01, value=_num(row.get("exit_fees")))
                            try:
                                default_exit = pd.to_datetime(row.get("exit_date")).date()
                            except Exception:
                                default_exit = date.today()
                            exit_date = st.date_input("تاريخ البيع", default_exit)
                        submitted = st.form_submit_button("حفظ التعديلات")
                    if submitted:
                        valid, message = validate_trade_inputs(quantity, entry_price)
                        if not valid:
                            st.error(message)
                        elif update_trade(
                            trade_id, quantity=quantity, entry_price=entry_price, trade_date=str(trade_date), entry_fees=entry_fees,
                            exit_price=exit_price, exit_date=str(exit_date) if exit_date else None, exit_fees=exit_fees, notes=notes,
                        ):
                            st.success("تم تحديث الصفقة.")
                            _clear_and_rerun()
                        else:
                            st.error("فشل تحديث الصفقة أو أنها لا تخص المستخدم الحالي.")

        st.markdown("---")
        if st.button("➕ إضافة صفقة", key=f"add_{key}", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with tab_archive:
        if closed_positions.empty:
            st.info("الأرشيف فارغ.")
        else:
            render_custom_table(
                closed_positions.sort_values("exit_date", ascending=False) if "exit_date" in closed_positions.columns else closed_positions,
                [("company_name", "الشركة", "text"), ("symbol", "الرمز", "text"), ("quantity", "الكمية", "number"),
                 ("entry_price", "سعر الشراء", "money"), ("exit_price", "سعر البيع", "money"), ("gain", "الربح المحقق", "colorful"),
                 ("gain_pct", "العائد %", "percent"), ("exit_date", "تاريخ البيع", "date")],
            )


def render_pulse_dashboard() -> None:
    username = current_username()
    from tenant_db import fetch_user_table

    trades = fetch_user_table("trades", username)
    symbols = [str(x).strip() for x in trades.get("symbol", pd.Series(dtype=str)).dropna().unique().tolist() if str(x).strip()]
    quotes = fetch_batch_data(symbols)
    if not symbols:
        st.info("لا توجد رموز لعرض نبض المحفظة.")
        return
    st.header("نبض المحفظة")
    columns = st.columns(4)
    for index, symbol in enumerate(symbols):
        norm = get_ticker_symbol(symbol)
        quote = quotes.get(symbol.upper()) or quotes.get(norm.upper()) or {}
        with columns[index % 4]:
            render_ticker_card(symbol, "سهم", quote.get("price") if quote.get("price") is not None else "-", quote.get("change_pct") if quote.get("change_pct") is not None else 0.0)
            st.caption(f"المصدر: {quote.get('source', 'غير متاح')}")


def view_add_trade() -> None:
    current_username()
    st.header("➕ إضافة صفقة")
    with st.form("add_trade_v2"):
        c1, c2 = st.columns(2)
        raw_symbol = c1.text_input("رمز السهم، مثال 1120")
        trade_type = c2.selectbox("نوع الصفقة", ["استثمار", "مضاربة", "صكوك"])
        c3, c4, c5 = st.columns(3)
        quantity = c3.number_input("الكمية", min_value=0.001, step=0.001)
        entry_price = c4.number_input("سعر الشراء", min_value=0.0, step=0.01)
        trade_date = c5.date_input("التاريخ", date.today())
        entry_fees = st.number_input("رسوم الدخول", min_value=0.0, step=0.01)
        notes = st.text_area("ملاحظات")
        submitted = st.form_submit_button("حفظ", use_container_width=True)

    if not submitted:
        return
    valid, message = validate_trade_inputs(quantity, entry_price)
    if not valid:
        st.error(message)
        return
    symbol = get_ticker_symbol(raw_symbol)
    if not symbol:
        st.error("أدخل رمزًا صحيحًا.")
        return

    name, sector = symbol, ""
    try:
        info = get_company_details(symbol)
        if isinstance(info, dict):
            name = info.get("name") or info.get("Name") or symbol
            sector = info.get("sector") or info.get("Sector") or ""
        elif isinstance(info, (tuple, list)) and len(info) >= 2:
            name, sector = info[0] or symbol, info[1] or ""
    except Exception:
        pass

    asset_type = "Sukuk" if trade_type == "صكوك" else "Stock"
    if insert_trade(symbol=symbol, company_name=str(name), sector=str(sector), asset_type=asset_type, quantity=quantity, entry_price=entry_price, strategy=trade_type, trade_date=str(trade_date), entry_fees=entry_fees, notes=notes):
        st.success("تم حفظ الصفقة.")
        _clear_and_rerun()
    else:
        st.error("لم تُحفظ الصفقة. راجع قاعدة البيانات.")
