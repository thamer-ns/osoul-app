"""Portfolio views with safe editing, partial exits and tenant-aware writes."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Tuple

import pandas as pd
import streamlit as st

from components import (
    render_custom_table,
    render_kpi,
    render_ticker_card,
    safe_fmt,
)
from data_source import get_company_details
from database import execute_query, fetch_table, get_connection, put_connection
from market_data import fetch_batch_data
from security import validate_trade_inputs
from tenant_scope import current_tenant
from views.shared import (
    _clean_symbols_list,
    _normalize_symbol,
    _safe_status_series,
)

try:
    from ai_engine_core.portfolio import (
        calculate_portfolio_risk_score,
        generate_rebalancing_suggestions,
        portfolio_risk_gates,
        run_stress_test,
    )
except Exception:
    calculate_portfolio_risk_score = None
    generate_rebalancing_suggestions = None
    portfolio_risk_gates = None
    run_stress_test = None


def _sf(value: Any, default: Any = 0.0):
    try:
        number = float(value)
        return number if pd.notna(number) else default
    except Exception:
        return default


def _status_text(value: object) -> str:
    closed_values = {
        "close",
        "closed",
        "sold",
        "مغلقة",
        "مغلق",
    }
    return (
        "مغلقة"
        if str(value or "").strip().lower() in closed_values
        else "مفتوحة"
    )


def _refresh_open_positions(
    positions: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    if positions is None or positions.empty:
        return (
            pd.DataFrame() if positions is None else positions,
            {},
        )
    frame = positions.copy()
    for column in (
        "quantity",
        "entry_price",
        "current_price",
        "total_cost",
    ):
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        ).fillna(0.0)
    if "symbol" not in frame.columns:
        frame["symbol"] = ""
    frame["symbol"] = frame["symbol"].astype(str).apply(_normalize_symbol)
    symbols = _clean_symbols_list(frame["symbol"].tolist())
    live = fetch_batch_data(symbols) if symbols else {}

    prices = []
    previous_prices = []
    sources = []
    stale_flags = []
    fetched_times = []
    for _, row in frame.iterrows():
        symbol = str(row.get("symbol") or "").upper()
        payload = (
            live.get(symbol)
            or live.get(_normalize_symbol(symbol))
            or {}
        )
        price = _sf(payload.get("price"), 0.0)
        fallback = _sf(
            row.get("current_price"),
            _sf(row.get("entry_price"), 0.0),
        )
        price = price if price > 0 else fallback
        prices.append(price)
        previous_prices.append(_sf(payload.get("prev_close"), 0.0))
        sources.append(str(payload.get("source") or "غير متاح"))
        stale_flags.append(bool(payload.get("is_stale", price <= 0)))
        fetched_times.append(str(payload.get("fetched_at") or "—"))

    frame["current_price"] = prices
    frame["prev_close"] = previous_prices
    frame["price_source"] = sources
    frame["price_stale"] = stale_flags
    frame["price_fetched_at"] = fetched_times
    frame["total_cost"] = frame["quantity"] * frame["entry_price"]
    frame["market_value"] = frame["quantity"] * frame["current_price"]
    frame["gain"] = frame["market_value"] - frame["total_cost"]
    frame["gain_pct"] = (
        frame["gain"]
        .div(frame["total_cost"].replace(0, pd.NA))
        .mul(100)
        .fillna(0.0)
    )
    frame["day_change"] = (
        (frame["current_price"] - frame["prev_close"])
        .div(frame["prev_close"].replace(0, pd.NA))
        .mul(100)
    )
    frame["status_ar"] = "مفتوحة"
    return frame, live


def _execute_or_error(
    query: str,
    params: tuple,
    success_message: str,
) -> bool:
    if execute_query(query, params):
        st.success(success_message)
        st.cache_data.clear()
        return True
    st.error("لم تُحفظ العملية في قاعدة البيانات. لم تتغير البيانات.")
    return False


def _close_trade_transaction(
    row: pd.Series,
    sell_quantity: float,
    exit_price: float,
    exit_date: date,
) -> bool:
    tenant = current_tenant()
    if tenant is None:
        return False
    trade_id = int(row["id"])
    original_quantity = _sf(row.get("quantity"))
    if not 0 < sell_quantity <= original_quantity:
        return False

    conn, kind = get_connection()
    try:
        cursor = conn.cursor()
        placeholder = "%s" if kind == "postgres" else "?"
        tenant_where = (
            f"id={placeholder} AND user_id={placeholder} "
            f"AND portfolio_id={placeholder} AND quantity={placeholder} "
            "AND LOWER(status)='open'"
        )
        if abs(sell_quantity - original_quantity) < 1e-9:
            query = (
                "UPDATE trades SET status='Close', "
                f"exit_price={placeholder}, exit_date={placeholder}, "
                f"current_price={placeholder}, "
                "updated_at=CURRENT_TIMESTAMP "
                f"WHERE {tenant_where}"
            )
            cursor.execute(
                query,
                (
                    exit_price,
                    str(exit_date),
                    exit_price,
                    trade_id,
                    tenant.user_id,
                    tenant.portfolio_id,
                    original_quantity,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("تم تغيير الصفقة قبل إتمام البيع")
        else:
            remaining = original_quantity - sell_quantity
            update_query = (
                f"UPDATE trades SET quantity={placeholder}, "
                "updated_at=CURRENT_TIMESTAMP "
                f"WHERE {tenant_where}"
            )
            cursor.execute(
                update_query,
                (
                    remaining,
                    trade_id,
                    tenant.user_id,
                    tenant.portfolio_id,
                    original_quantity,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("تم تغيير الصفقة قبل إتمام البيع")

            insert_query = (
                "INSERT INTO trades "
                "(symbol, company_name, sector, asset_type, quantity, "
                "entry_price, exit_price, current_price, strategy, "
                "status, date, exit_date, created_at, updated_at, "
                "user_id, portfolio_id) "
                f"VALUES ({','.join([placeholder] * 16)})"
            )
            bought_at = pd.to_datetime(
                row.get("date"),
                errors="coerce",
            )
            now = str(pd.Timestamp.utcnow())
            cursor.execute(
                insert_query,
                (
                    row.get("symbol"),
                    row.get("company_name"),
                    row.get("sector"),
                    row.get("asset_type"),
                    sell_quantity,
                    row.get("entry_price"),
                    exit_price,
                    exit_price,
                    row.get("strategy"),
                    "Close",
                    str(bought_at.date())
                    if pd.notna(bought_at)
                    else str(date.today()),
                    str(exit_date),
                    now,
                    now,
                    tenant.user_id,
                    tenant.portfolio_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("تعذر إنشاء سجل البيع الجزئي")
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            import logging
            logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
        return False
    finally:
        put_connection(conn, kind)


def _render_risk_panel(
    finance: dict,
    positions: pd.DataFrame,
    total_market: float,
) -> None:
    with st.expander(
        "🛡️ مخاطر المحفظة واختبار الضغط",
        expanded=True,
    ):
        cash = _sf((finance or {}).get("cash"))
        portfolio_value = _sf(
            (finance or {}).get("portfolio_value"),
            cash + total_market,
        )
        cash_pct = cash / portfolio_value * 100 if portfolio_value > 0 else 0.0
        risk_score = None
        if callable(calculate_portfolio_risk_score) and not positions.empty:
            try:
                risk_score = _sf(
                    calculate_portfolio_risk_score(positions, cash_pct),
                    None,
                )
            except Exception:
                risk_score = None

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi("قيمة المحفظة", safe_fmt(portfolio_value), "blue")
        with c2:
            render_kpi("الكاش", safe_fmt(cash), "neutral")
        with c3:
            render_kpi(
                "نسبة الكاش",
                f"{cash_pct:.1f}%",
                "success" if cash_pct >= 15 else "danger",
                "٪",
            )
        with c4:
            render_kpi(
                "درجة المخاطر",
                "غير متاح"
                if risk_score is None
                else f"{risk_score:.0f}/100",
                "neutral"
                if risk_score is None
                else "danger"
                if risk_score >= 70
                else "success",
            )

        xirr = (finance or {}).get("xirr")
        xirr_note = str((finance or {}).get("xirr_note") or "")
        if xirr is not None:
            st.metric("العائد السنوي المرجح نقديًا XIRR", f"{_sf(xirr) * 100:.2f}%")
            st.caption(
                "يعتمد على الإيداعات والسحوبات والقيمة الحالية؛ "
                "التوزيعات التي بقيت داخل المحفظة لا تُحتسب مرتين."
            )
        elif xirr_note:
            st.caption(f"XIRR غير متاح: {xirr_note}")

        gates = {"pass": True, "reasons": []}
        if callable(portfolio_risk_gates) and not positions.empty:
            try:
                gates = portfolio_risk_gates(positions, cash_pct) or gates
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
        if gates.get("pass", True):
            st.success("بوابات المخاطر: الوضع مقبول")
        else:
            st.warning("بوابات المخاطر: يلزم تخفيف المخاطر")
            for reason in (gates.get("reasons") or [])[:8]:
                st.write(f"- {reason}")

        if callable(run_stress_test):
            try:
                stress = run_stress_test(portfolio_value, positions) or {}
                scenarios = pd.DataFrame(stress.get("scenarios") or [])
                if not scenarios.empty:
                    st.markdown("**سيناريوهات اختبار الضغط**")
                    render_custom_table(scenarios)
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)

        suggestions = []
        if callable(generate_rebalancing_suggestions):
            try:
                suggestions = (
                    generate_rebalancing_suggestions(positions, cash_pct)
                    or []
                )
            except Exception:
                suggestions = []
        if suggestions:
            st.markdown("**اقتراحات إعادة التوازن**")
            for level, text in suggestions[:8]:
                if (
                    "danger" in str(level).lower()
                    or "priority" in str(level).lower()
                ):
                    st.warning(str(text))
                else:
                    st.info(str(text))


def _sort_open_positions(positions: pd.DataFrame, key: str) -> pd.DataFrame:
    selected = st.selectbox(
        "فرز المراكز حسب",
        [
            "الربح الأعلى",
            "القيمة الأعلى",
            "العائد الأعلى",
            "التغير اليومي الأعلى",
            "التاريخ الأحدث",
            "الشركة",
        ],
        key=f"portfolio_sort_{key}",
    )
    mapping = {
        "الربح الأعلى": ("gain", False),
        "القيمة الأعلى": ("market_value", False),
        "العائد الأعلى": ("gain_pct", False),
        "التغير اليومي الأعلى": ("day_change", False),
        "التاريخ الأحدث": ("date", False),
        "الشركة": ("company_name", True),
    }
    column, ascending = mapping[selected]
    if column in positions.columns:
        return positions.sort_values(column, ascending=ascending)
    return positions


def _render_open_table(positions: pd.DataFrame) -> None:
    render_custom_table(
        positions,
        [
            ("company_name", "الشركة", "text"),
            ("sector", "القطاع", "text"),
            ("symbol", "الرمز", "text"),
            ("date", "تاريخ الشراء", "date"),
            ("quantity", "الكمية", "number"),
            ("entry_price", "سعر الشراء", "money"),
            ("current_price", "السعر الحالي", "money"),
            ("market_value", "القيمة السوقية", "money"),
            ("gain", "الربح والخسارة", "colorful"),
            ("gain_pct", "العائد", "percent"),
            ("day_change", "التغير اليومي", "percent"),
            ("price_source", "مصدر السعر", "text"),
        ],
    )
    stale_count = int(
        positions.get("price_stale", pd.Series(dtype=bool))
        .fillna(False)
        .sum()
    )
    if stale_count:
        st.warning(
            f"يوجد {stale_count} مركز بسعر احتياطي أو قديم؛ "
            "راجع مصدر السعر قبل اتخاذ قرار."
        )


def _render_close_form(positions: pd.DataFrame, key: str) -> None:
    with st.expander("🔴 بيع كلي أو جزئي"):
        options = {
            f"{row.get('company_name') or row.get('symbol')} "
            f"({row.get('symbol')}) — {row.get('quantity')} سهم": int(row["id"])
            for _, row in positions.iterrows()
            if pd.notna(row.get("id"))
        }
        if not options:
            st.info("لا توجد صفقات مفتوحة")
            return
        label = st.selectbox(
            "اختر الصفقة",
            list(options),
            key=f"sell_select_{key}",
        )
        row = positions[positions["id"] == options[label]].iloc[0]
        with st.form(f"sell_form_{key}_{int(row['id'])}"):
            quantity = st.number_input(
                "كمية البيع",
                min_value=0.001,
                max_value=float(row["quantity"]),
                value=float(row["quantity"]),
                step=0.001,
            )
            price = st.number_input(
                "سعر البيع",
                min_value=0.01,
                value=max(
                    0.01,
                    _sf(
                        row.get("current_price"),
                        _sf(row.get("entry_price")),
                    ),
                ),
                step=0.01,
            )
            sold_at = st.date_input("تاريخ البيع", date.today())
            submitted = st.form_submit_button(
                "تأكيد البيع",
                type="primary",
            )
        if submitted:
            valid, message = validate_trade_inputs(quantity, price)
            if not valid:
                st.error(message)
            elif _close_trade_transaction(row, quantity, price, sold_at):
                st.success(
                    "تم تسجيل البيع"
                    if quantity == float(row["quantity"])
                    else "تم البيع الجزئي وإنشاء سجل مغلق مستقل"
                )
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(
                    "تعذر تسجيل البيع؛ ربما تغيرت الكمية في جلسة أخرى. "
                    "حدّث الصفحة وأعد المحاولة."
                )


def _render_edit_form(
    open_positions: pd.DataFrame,
    closed_positions: pd.DataFrame,
    key: str,
) -> None:
    with st.expander("✏️ تعديل صفقة مفتوحة أو مغلقة"):
        edit_frame = (
            pd.concat(
                [open_positions, closed_positions],
                ignore_index=True,
            ).drop_duplicates(subset=["id"])
            if not closed_positions.empty
            else open_positions.copy()
        )
        if edit_frame.empty or "id" not in edit_frame.columns:
            st.info("لا توجد صفقات للتعديل")
            return
        options = {}
        for _, row in edit_frame.iterrows():
            trade_id = row.get("id")
            if pd.isna(trade_id):
                continue
            company = (
                row.get("company_name")
                or row.get("symbol")
                or "بدون اسم"
            )
            options[
                f"[{_status_text(row.get('status'))}] {company} "
                f"({row.get('symbol')}) — ID:{int(trade_id)}"
            ] = int(trade_id)
        selected = st.selectbox(
            "اختر الصفقة",
            list(options),
            key=f"edit_select_{key}",
        )
        row = edit_frame[edit_frame["id"] == options[selected]].iloc[0]
        closed = _status_text(row.get("status")) == "مغلقة"
        with st.form(f"edit_form_{key}_{int(row['id'])}"):
            quantity = st.number_input(
                "الكمية",
                min_value=0.001,
                value=max(0.001, _sf(row.get("quantity"), 1.0)),
                step=0.001,
            )
            entry_price = st.number_input(
                "سعر الشراء",
                min_value=0.01,
                value=max(0.01, _sf(row.get("entry_price"), 0.01)),
                step=0.01,
            )
            parsed_buy = pd.to_datetime(row.get("date"), errors="coerce")
            buy_date = st.date_input(
                "تاريخ الشراء",
                parsed_buy.date()
                if pd.notna(parsed_buy)
                else date.today(),
            )
            exit_price = None
            exit_date = None
            if closed:
                exit_price = st.number_input(
                    "سعر البيع",
                    min_value=0.01,
                    value=max(
                        0.01,
                        _sf(row.get("exit_price"), 0.01),
                    ),
                    step=0.01,
                )
                parsed_exit = pd.to_datetime(
                    row.get("exit_date"),
                    errors="coerce",
                )
                exit_date = st.date_input(
                    "تاريخ البيع",
                    parsed_exit.date()
                    if pd.notna(parsed_exit)
                    else date.today(),
                )
            submitted = st.form_submit_button("حفظ التعديل")
        if submitted:
            valid, message = validate_trade_inputs(
                quantity,
                entry_price,
            )
            if not valid:
                st.error(message)
                return
            if closed:
                valid_exit, exit_message = validate_trade_inputs(
                    quantity,
                    exit_price,
                )
                if not valid_exit:
                    st.error(exit_message)
                    return
                saved = _execute_or_error(
                    "UPDATE trades SET quantity=%s, entry_price=%s, "
                    "date=%s, exit_price=%s, exit_date=%s, "
                    "current_price=%s, updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=%s",
                    (
                        quantity,
                        entry_price,
                        str(buy_date),
                        exit_price,
                        str(exit_date),
                        exit_price,
                        int(row["id"]),
                    ),
                    "تم تعديل الصفقة المغلقة",
                )
            else:
                saved = _execute_or_error(
                    "UPDATE trades SET quantity=%s, entry_price=%s, "
                    "date=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                    (
                        quantity,
                        entry_price,
                        str(buy_date),
                        int(row["id"]),
                    ),
                    "تم تعديل الصفقة المفتوحة",
                )
            if saved:
                st.rerun()


def view_portfolio(finance, key):
    title = "مضاربة" if key == "spec" else "استثمار"
    st.header(f"💼 محفظة {title}")
    trades = (
        finance.get("all_trades", pd.DataFrame())
        if isinstance(finance, dict)
        else pd.DataFrame()
    )
    if trades.empty:
        subset = pd.DataFrame()
    elif "strategy" in trades.columns:
        subset = trades[
            trades["strategy"].astype(str).str.contains(title, na=False)
        ].copy()
    else:
        subset = trades.copy()

    status = (
        _safe_status_series(subset)
        if not subset.empty
        else pd.Series(dtype=str)
    )
    open_positions = (
        subset[status == "open"].copy()
        if len(status)
        else pd.DataFrame()
    )
    closed_positions = (
        subset[status.isin(["close", "closed"])].copy()
        if len(status)
        else pd.DataFrame()
    )
    open_positions, _ = _refresh_open_positions(open_positions)

    open_tab, archive_tab = st.tabs(["الصفقات القائمة", "الأرشيف"])
    with open_tab:
        total_cost = _sf(
            open_positions.get(
                "total_cost",
                pd.Series(dtype=float),
            ).sum()
        )
        total_market = _sf(
            open_positions.get(
                "market_value",
                pd.Series(dtype=float),
            ).sum()
        )
        total_gain = total_market - total_cost
        total_return = total_gain / total_cost * 100 if total_cost else 0.0
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral")
        with c2:
            render_kpi("القيمة السوقية", safe_fmt(total_market), "blue")
        with c3:
            render_kpi(
                "الربح والخسارة",
                safe_fmt(total_gain),
                "success" if total_gain >= 0 else "danger",
            )
        with c4:
            render_kpi(
                "العائد",
                f"{total_return:.2f}%",
                "success" if total_return >= 0 else "danger",
                "٪",
            )
        _render_risk_panel(finance or {}, open_positions, total_market)
        if open_positions.empty:
            st.info("لا توجد صفقات قائمة")
        else:
            open_positions = _sort_open_positions(open_positions, key)
            _render_open_table(open_positions)
            left, right = st.columns(2)
            with left:
                _render_close_form(open_positions, key)
            with right:
                _render_edit_form(
                    open_positions,
                    closed_positions,
                    key,
                )
        if st.button(
            "➕ إضافة سهم",
            key=f"add_{key}",
            type="primary",
        ):
            st.session_state.page = "add"
            st.rerun()

    with archive_tab:
        if closed_positions.empty:
            st.info("الأرشيف فارغ")
        else:
            closed = closed_positions.copy()
            for column in ("quantity", "entry_price", "exit_price"):
                if column not in closed.columns:
                    closed[column] = 0.0
                closed[column] = pd.to_numeric(
                    closed[column],
                    errors="coerce",
                ).fillna(0.0)
            closed["total_cost"] = closed["quantity"] * closed["entry_price"]
            closed["sale_value"] = closed["quantity"] * closed["exit_price"]
            closed["gain"] = closed["sale_value"] - closed["total_cost"]
            closed["gain_pct"] = (
                closed["gain"]
                .div(closed["total_cost"].replace(0, pd.NA))
                .mul(100)
                .fillna(0.0)
            )
            archive_sort = st.selectbox(
                "فرز الأرشيف حسب",
                ["تاريخ البيع الأحدث", "الربح الأعلى", "العائد الأعلى"],
                key=f"archive_sort_{key}",
            )
            if archive_sort == "الربح الأعلى":
                closed = closed.sort_values("gain", ascending=False)
            elif archive_sort == "العائد الأعلى":
                closed = closed.sort_values("gain_pct", ascending=False)
            elif "exit_date" in closed.columns:
                closed = closed.sort_values("exit_date", ascending=False)
            render_custom_table(
                closed,
                [
                    ("company_name", "الشركة", "text"),
                    ("symbol", "الرمز", "text"),
                    ("quantity", "الكمية", "number"),
                    ("entry_price", "سعر الشراء", "money"),
                    ("exit_price", "سعر البيع", "money"),
                    ("gain", "الربح", "colorful"),
                    ("gain_pct", "العائد", "percent"),
                    ("exit_date", "تاريخ البيع", "date"),
                ],
            )


def render_pulse_dashboard():
    st.header("نبض المحفظة")
    trades = fetch_table("trades")
    symbols = (
        _clean_symbols_list(
            trades["symbol"].dropna().astype(str).unique().tolist()
        )
        if isinstance(trades, pd.DataFrame)
        and not trades.empty
        and "symbol" in trades.columns
        else []
    )
    data = fetch_batch_data(symbols) if symbols else {}
    if not data:
        st.info("لا توجد رموز للعرض")
        return
    columns = st.columns(4)
    shown = set()
    index = 0
    for symbol in symbols:
        payload = (
            data.get(symbol)
            or data.get(_normalize_symbol(symbol))
            or {}
        )
        normalized = str(payload.get("symbol") or symbol)
        if normalized in shown:
            continue
        shown.add(normalized)
        change = payload.get("change_pct")
        with columns[index % 4]:
            render_ticker_card(
                normalized,
                str(payload.get("source") or "سهم"),
                payload.get("price"),
                0.0 if change is None else change,
            )
            if change is None:
                st.caption("التغير اليومي غير متاح")
        index += 1


def view_add_trade():
    st.header("➕ إضافة صفقة")
    with st.form("add_trade_form"):
        c1, c2 = st.columns(2)
        raw_symbol = c1.text_input("رمز السهم، مثال 1120")
        strategy = c2.selectbox(
            "نوع الصفقة",
            ["استثمار", "مضاربة", "صكوك"],
        )
        c3, c4, c5 = st.columns(3)
        quantity = c3.number_input(
            "الكمية",
            min_value=0.001,
            step=0.001,
        )
        price = c4.number_input(
            "سعر الشراء",
            min_value=0.01,
            step=0.01,
        )
        bought_at = c5.date_input("تاريخ الشراء", date.today())
        submitted = st.form_submit_button("حفظ", type="primary")
    if not submitted:
        return
    valid, message = validate_trade_inputs(quantity, price)
    if not valid:
        st.error(message)
        return
    symbol = _normalize_symbol(raw_symbol)
    if not symbol:
        st.error("أدخل رمزًا صحيحًا")
        return
    try:
        info = get_company_details(symbol)
        if isinstance(info, dict):
            name = info.get("name") or info.get("Name") or symbol
            sector = info.get("sector") or info.get("Sector") or ""
        elif isinstance(info, (tuple, list)) and len(info) >= 2:
            name = info[0] or symbol
            sector = info[1] or ""
        else:
            name, sector = symbol, ""
    except Exception:
        name, sector = symbol, ""
    asset_type = "Sukuk" if strategy == "صكوك" else "Stock"
    if _execute_or_error(
        "INSERT INTO trades "
        "(symbol, company_name, sector, asset_type, quantity, "
        "entry_price, current_price, strategy, status, date, "
        "created_at, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s,"
        "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
        (
            symbol,
            name,
            sector,
            asset_type,
            quantity,
            price,
            price,
            strategy,
            str(bought_at),
        ),
        "تمت إضافة الصفقة",
    ):
        st.rerun()
