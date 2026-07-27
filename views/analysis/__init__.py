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

TIMEFRAME_OPTIONS = {
    "1 دقيقة": "1m",
    "5 دقائق": "5m",
    "15 دقيقة": "15m",
    "30 دقيقة": "30m",
    "ساعة": "1h",
    "4 ساعات": "4h",
    "يومي": "1d",
    "أسبوعي": "1wk",
    "شهري": "1mo",
}

# module, renderer, title, receives timeframe
SECTION_ROUTES = {
    "🧭 النظرة الموحدة": ("views.analysis.overview", "render_unified_overview", "النظرة الموحدة", True),
    "🤖 المستشار": ("views.analysis.advisor", "render_advisor_tab", "المستشار", True),
    "📈 التحليل الفني": ("views.analysis.technical", "render_technical_tab", "التحليل الفني", True),
    "💰 التحليل المالي": ("views.analysis.financial", "render_financial_dashboard_ui", "التحليل المالي", False),
    "🏛️ التحليل الكلاسيكي": ("views.analysis.classical", "render_classical_tab", "التحليل الكلاسيكي", False),
    "📝 الأطروحة والخطة": ("views.analysis.thesis", "render_thesis_tab", "الأطروحة", False),
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
                "is_stale": bool(payload.get("is_stale", payload.get("price_stale", False))),
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
                    "is_stale": bool(lineage.get("is_stale", False)),
                }
    except Exception:
        logger.exception("history fallback failed for %s", normalized)
    return {"price": None, "change": None, "source": "غير متاح", "fetched_at": "—", "is_stale": True}


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
        if st.button("إزالة من قائمة المراقبة", use_container_width=True, key=f"analysis_watch_remove:{symbol}"):
            if execute_query("DELETE FROM watchlist WHERE symbol=%s", (symbol,)):
                st.success("تمت الإزالة من قائمة المراقبة")
                st.cache_data.clear()
                st.rerun()
            st.error("تعذر إزالة الرمز")
    elif st.button("إضافة إلى قائمة المراقبة", use_container_width=True, key=f"analysis_watch_add:{symbol}"):
        if execute_query(
            "INSERT INTO watchlist (symbol, created_at) VALUES (%s,CURRENT_TIMESTAMP) "
            "ON CONFLICT (symbol) DO NOTHING",
            (symbol,),
        ):
            st.success("تمت الإضافة إلى قائمة المراقبة")
            st.cache_data.clear()
            st.rerun()
        st.info("الرمز موجود مسبقًا أو تعذر حفظه")


def _render_header(symbol: str, name: str, sector: str, trades: pd.DataFrame, watchlist: pd.DataFrame, interval: str) -> None:
    snapshot = _price_snapshot(symbol)
    price, change = snapshot.get("price"), snapshot.get("change")
    st.subheader(name or symbol)
    stale_note = " — السعر قديم" if snapshot.get("is_stale") else ""
    st.caption(
        f"{symbol} — {sector or 'قطاع غير متاح'} — الفاصل: {interval} — "
        f"المصدر: {snapshot.get('source')} — وقت الجلب: {snapshot.get('fetched_at')}{stale_note}"
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
        render_kpi("وقت العرض", datetime.now(timezone.utc).strftime("%H:%M UTC"), "neutral", "🕒")
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


def _render_diagnostics(symbol: str, interval: str) -> None:
    st.subheader("تشخيص بيانات الرمز")
    snapshot = _price_snapshot(symbol)
    if snapshot.get("price") is None:
        st.warning("تعذر جلب سعر صالح من المصادر الحالية.")
    else:
        st.success(f"السعر متاح: {float(snapshot['price']):,.2f} — المصدر: {snapshot.get('source')}")
    try:
        period = "7d" if interval == "1m" else "60d" if interval in {"5m", "15m", "30m"} else "2y" if interval in {"1h", "4h"} else "10y" if interval in {"1wk", "1mo"} else "3y"
        history = get_chart_history(symbol, period=period, interval=interval)
        attrs = getattr(history, "attrs", {}) or {} if isinstance(history, pd.DataFrame) else {}
        lineage = attrs.get("data_lineage") or {}
        rows = [
            {"البند": "عدد الشموع", "القيمة": len(history) if isinstance(history, pd.DataFrame) else 0},
            {"البند": "المصدر", "القيمة": lineage.get("source") or attrs.get("source") or "غير معروف"},
            {"البند": "وقت الجلب", "القيمة": lineage.get("fetched_at") or "—"},
            {"البند": "الفاصل", "القيمة": interval},
        ]
        render_custom_table(pd.DataFrame(rows))
    except Exception:
        st.warning("تعذر اختبار تاريخ الأسعار.")


def view_analysis(fin):
    finance = fin or {}
    trades = finance.get("all_trades", pd.DataFrame())
    watchlist = _watchlist()

    st.header("🔬 التحليل الشامل")
    st.caption("ابدأ بالنظرة الموحدة، ثم افتح القسم المتخصص عند الحاجة. الأقسام الثقيلة تعمل عند الطلب فقط.")
    _render_stress_on_demand(finance, trades)

    universe = _symbol_universe(trades, watchlist)
    current_interval = str(st.session_state.get("analysis_active_interval") or "1d")
    labels = list(TIMEFRAME_OPTIONS)
    current_label = next((label for label, value in TIMEFRAME_OPTIONS.items() if value == current_interval), "يومي")
    with st.form("analysis_symbol_form"):
        c1, c2, c3, c4 = st.columns([1.3, 1.8, 1.2, .8])
        raw_symbol = c1.text_input("رمز جديد", placeholder="1120 أو 1120.SR")
        selected = c2.selectbox("من المحفظة والمراقبة", options=universe or ["—"], disabled=not universe)
        timeframe_label = c3.selectbox("الفاصل", options=labels, index=labels.index(current_label))
        submitted = c4.form_submit_button("تطبيق", type="primary")

    if submitted:
        candidate = raw_symbol.strip() or (selected if selected != "—" else st.session_state.get("analysis_active_symbol", ""))
        normalized = normalize_symbol(candidate)
        if not normalized or normalized == ".SR":
            st.error("أدخل رمزًا صحيحًا مثل 1120 أو 1120.SR")
        else:
            st.session_state["analysis_active_symbol"] = normalized
            st.session_state["analysis_active_interval"] = TIMEFRAME_OPTIONS[timeframe_label]
            st.rerun()

    symbol = normalize_symbol(st.session_state.get("analysis_active_symbol"))
    interval = str(st.session_state.get("analysis_active_interval") or "1d")
    if not symbol or symbol == ".SR":
        st.info("اختر رمزًا وفاصلًا لبدء التحليل.")
        return

    name, sector = _company_meta(symbol)
    _render_header(symbol, name, sector, trades, watchlist, interval)

    sections = list(SECTION_ROUTES) + ["🩺 تشخيص البيانات"]
    section = st.radio(
        "قسم التحليل",
        sections,
        horizontal=True,
        label_visibility="collapsed",
        key=f"analysis_section_{symbol}",
    )
    if section == "🩺 تشخيص البيانات":
        _render_diagnostics(symbol, interval)
        return
    module_name, attr_name, title, receives_timeframe = SECTION_ROUTES[section]
    args = (symbol, interval) if receives_timeframe else (symbol,)
    _safe_render(title, module_name, attr_name, *args)
