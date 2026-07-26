"""Lazy comprehensive-analysis workspace."""
from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi
from data_source import get_company_details
from database import execute_query, fetch_table
from market_data import fetch_batch_data, get_chart_history, get_ticker_symbol
from views.utils import clean_symbols, normalize_symbol, safe_status_series

logger = logging.getLogger("osoli.analysis")

SECTION_ROUTES = {
    "🤖 المستشار": ("views.analysis.advisor", "render_advisor_tab", "المستشار"),
    "💰 التحليل المالي": ("views.analysis.financial", "render_financial_dashboard_ui", "التحليل المالي"),
    "📈 التحليل الفني": ("views.analysis.technical", "render_technical_tab", "التحليل الفني"),
    "🏛️ التحليل الكلاسيكي": ("views.analysis.classical", "render_classical_tab", "التحليل الكلاسيكي"),
    "📝 الأطروحة والخطة": ("views.analysis.thesis", "render_thesis_tab", "الأطروحة"),
}


def _number(value: Any, default: float | None = 0.0):
    try:
        return float(value)
    except Exception:
        return default


@st.cache_data(ttl=300, max_entries=256, show_spinner=False)
def _company_details(symbol: str):
    return get_company_details(symbol)


@st.cache_data(ttl=90, max_entries=256, show_spinner=False)
def _price_snapshot(symbol: str) -> dict:
    normalized = get_ticker_symbol(symbol) or normalize_symbol(symbol)
    try:
        batch = fetch_batch_data([normalized]) or {}
        payload = batch.get(normalized) or batch.get(normalized.upper()) or {}
        price = _number(payload.get("price"), None)
        previous = _number(payload.get("prev_close", payload.get("previous_close")), None)
        change = None
        if price is not None and previous is not None and previous > 0:
            change = (price / previous - 1.0) * 100.0
        elif payload.get("change_pct") is not None:
            change = _number(payload.get("change_pct"), None)
        if price is not None and price > 0:
            return {
                "price": price,
                "change": change,
                "source": str(payload.get("source") or "غير معروف"),
                "fetched_at": str(payload.get("fetched_at") or "—"),
            }
    except Exception:
        logger.exception("snapshot failed for %s", normalized)

    try:
        history = get_chart_history(normalized, period="5d", interval="1d")
        if isinstance(history, pd.DataFrame) and not history.empty and "Close" in history.columns:
            close = pd.to_numeric(history["Close"], errors="coerce").dropna()
            if not close.empty:
                price = float(close.iloc[-1])
                previous = float(close.iloc[-2]) if len(close) > 1 else None
                change = (price / previous - 1.0) * 100.0 if previous and previous > 0 else None
                attrs = getattr(history, "attrs", {}) or {}
                lineage = attrs.get("data_lineage") or {}
                return {
                    "price": price,
                    "change": change,
                    "source": str(lineage.get("source") or attrs.get("source") or "history"),
                    "fetched_at": str(lineage.get("fetched_at") or "—"),
                }
    except Exception:
        logger.exception("history fallback failed for %s", normalized)
    return {"price": None, "change": None, "source": "غير متاح", "fetched_at": "—"}


def _company_meta(symbol: str) -> tuple[str, str]:
    try:
        info = _company_details(symbol)
        if isinstance(info, dict):
            return str(info.get("name") or info.get("Name") or symbol), str(info.get("sector") or info.get("Sector") or "")
        if isinstance(info, (list, tuple)):
            name = str(info[0] or symbol) if len(info) else symbol
            sector = str(info[1] or "") if len(info) > 1 else ""
            return name, sector
        if info:
            return str(info), ""
    except Exception:
        logger.exception("company metadata failed for %s", symbol)
    return symbol, ""


def _safe_render(title: str, module_name: str, attr_name: str, *args) -> None:
    try:
        renderer = getattr(importlib.import_module(module_name), attr_name)
        renderer(*args)
    except Exception:
        logger.exception("analysis section failed: %s", title)
        st.error(f"تعذر تحميل قسم {title} الآن.")
        st.caption("تم تسجيل التفاصيل لدى الخادم دون عرض بيانات تقنية حساسة.")


def _watchlist() -> pd.DataFrame:
    try:
        value = fetch_table("watchlist")
        return value if isinstance(value, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _symbol_universe(trades: pd.DataFrame, watchlist: pd.DataFrame) -> list[str]:
    values: list[str] = []
    if isinstance(trades, pd.DataFrame) and not trades.empty and "symbol" in trades.columns:
        values.extend(trades["symbol"].dropna().astype(str).tolist())
    if isinstance(watchlist, pd.DataFrame) and not watchlist.empty and "symbol" in watchlist.columns:
        values.extend(watchlist["symbol"].dropna().astype(str).tolist())
    return clean_symbols(values)


def _render_watchlist_action(symbol: str, watchlist: pd.DataFrame) -> None:
    existing = set()
    if not watchlist.empty and "symbol" in watchlist.columns:
        existing = {normalize_symbol(value) for value in watchlist["symbol"].dropna().astype(str)}
    if symbol in existing:
        if st.button("إزالة من قائمة المراقبة", use_container_width=True):
            if execute_query("DELETE FROM watchlist WHERE symbol=%s", (symbol,)):
                st.success("تمت الإزالة من قائمة المراقبة")
                st.cache_data.clear()
                st.rerun()
            st.error("تعذر إزالة الرمز")
    elif st.button("إضافة إلى قائمة المراقبة", use_container_width=True):
        if execute_query(
            "INSERT INTO watchlist (symbol, created_at) VALUES (%s,CURRENT_TIMESTAMP) "
            "ON CONFLICT (symbol) DO NOTHING",
            (symbol,),
        ):
            st.success("تمت الإضافة إلى قائمة المراقبة")
            st.cache_data.clear()
            st.rerun()
        st.info("الرمز موجود مسبقًا أو تعذر حفظه")


def _render_header(symbol: str, name: str, sector: str, trades: pd.DataFrame, watchlist: pd.DataFrame) -> None:
    snapshot = _price_snapshot(symbol)
    price, change = snapshot.get("price"), snapshot.get("change")
    st.subheader(name or symbol)
    st.caption(
        f"{symbol} — {sector or 'قطاع غير متاح'} — المصدر: {snapshot.get('source')} — "
        f"وقت الجلب: {snapshot.get('fetched_at')}"
    )
    positions = pd.DataFrame()
    if isinstance(trades, pd.DataFrame) and not trades.empty:
        normalized = trades.get("symbol", pd.Series("", index=trades.index)).astype(str).map(normalize_symbol)
        status = safe_status_series(trades)
        positions = trades[(normalized == symbol) & (status == "open")]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("السعر", "—" if price is None else f"{float(price):,.2f}", "neutral", "💵")
    with c2:
        render_kpi(
            "التغير اليومي",
            "—" if change is None else f"{float(change):+.2f}%",
            "neutral" if change is None else "success" if change >= 0 else "danger",
            "📈",
        )
    with c3:
        render_kpi("المراكز المفتوحة", int(len(positions)), "blue", "📌")
    with c4:
        render_kpi("آخر تحديث", datetime.now(timezone.utc).strftime("%H:%M UTC"), "neutral", "🕒")
    _render_watchlist_action(symbol, watchlist)


def _render_stress_on_demand(finance: dict, trades: pd.DataFrame) -> None:
    status = safe_status_series(trades)
    open_positions = trades[status == "open"].copy() if isinstance(trades, pd.DataFrame) and not trades.empty else pd.DataFrame()
    if open_positions.empty:
        return
    with st.expander("📊 اختبار ضغط المحفظة", expanded=False):
        st.caption("لا يُنفذ الاختبار الحسابي إلا عند الطلب لتسريع فتح الصفحة.")
        if st.button("تشغيل اختبار الضغط", key="run_analysis_stress"):
            try:
                from ai_engine import run_stress_test

                result = run_stress_test(_number(finance.get("portfolio_value"), 0.0) or 0.0, open_positions) or {}
                st.session_state["analysis_stress_result"] = result
            except Exception:
                logger.exception("stress test failed")
                st.error("تعذر تشغيل اختبار الضغط الآن.")
        result = st.session_state.get("analysis_stress_result") or {}
        scenarios = pd.DataFrame(result.get("scenarios") or [])
        if not scenarios.empty:
            render_custom_table(scenarios)
            if result.get("insight"):
                st.info(str(result["insight"]))
            st.caption("اختبار تقديري للحساسية وليس توقعًا أو ضمانًا.")


def _render_diagnostics(symbol: str) -> None:
    st.subheader("تشخيص بيانات الرمز")
    snapshot = _price_snapshot(symbol)
    if snapshot.get("price") is None:
        st.warning("تعذر جلب سعر صالح من المصادر الحالية.")
    else:
        st.success(f"السعر متاح: {float(snapshot['price']):,.2f} — المصدر: {snapshot.get('source')}")
    try:
        history = get_chart_history(symbol, years=2, interval="1d")
        st.metric("عدد الشموع اليومية", len(history) if isinstance(history, pd.DataFrame) else 0)
    except Exception:
        st.warning("تعذر اختبار تاريخ الأسعار.")


def view_analysis(fin):
    finance = fin or {}
    trades = finance.get("all_trades", pd.DataFrame())
    watchlist = _watchlist()

    st.header("🔬 التحليل الشامل")
    st.caption("تحميل كسول لكل قسم: لا يتم استيراد أو حساب الأقسام الأخرى قبل اختيارها.")
    _render_stress_on_demand(finance, trades)

    universe = _symbol_universe(trades, watchlist)
    with st.form("analysis_symbol_form"):
        left, middle, right = st.columns([1.4, 2.2, 1])
        raw_symbol = left.text_input("رمز جديد", placeholder="1120 أو 1120.SR")
        selected = middle.selectbox(
            "من المحفظة وقائمة المراقبة",
            options=universe or ["—"],
            disabled=not universe,
        )
        submitted = right.form_submit_button("تحليل", type="primary")

    if submitted:
        candidate = raw_symbol.strip() or (selected if selected != "—" else "")
        normalized = normalize_symbol(candidate)
        if not normalized or normalized == ".SR":
            st.error("أدخل رمزًا صحيحًا مثل 1120 أو 1120.SR")
        else:
            st.session_state["analysis_active_symbol"] = normalized
            st.rerun()

    symbol = normalize_symbol(st.session_state.get("analysis_active_symbol"))
    if not symbol or symbol == ".SR":
        st.info("اختر رمزًا لبدء التحليل.")
        return

    name, sector = _company_meta(symbol)
    _render_header(symbol, name, sector, trades, watchlist)

    sections = list(SECTION_ROUTES) + ["🩺 تشخيص البيانات"]
    section = st.radio(
        "قسم التحليل",
        sections,
        horizontal=True,
        label_visibility="collapsed",
        key=f"analysis_section_{symbol}",
    )
    if section == "🩺 تشخيص البيانات":
        _render_diagnostics(symbol)
        return
    module_name, attr_name, title = SECTION_ROUTES[section]
    _safe_render(title, module_name, attr_name, symbol)
