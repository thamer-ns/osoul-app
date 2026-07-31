"""Stable entry point for the comprehensive analysis workspace."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

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


def _number(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


@st.cache_data(ttl=300, max_entries=256, show_spinner=False)
def _company_details(symbol: str) -> Any:
    return get_company_details(symbol)


@st.cache_data(ttl=90, max_entries=256, show_spinner=False)
def _price_snapshot(symbol: str) -> dict[str, Any]:
    """Return a quote without allowing provider failure to remove analysis UI."""
    normalized = get_ticker_symbol(symbol) or normalize_symbol(symbol)
    try:
        batch = fetch_batch_data([normalized]) or {}
        payload = batch.get(normalized) or batch.get(normalized.upper()) or {}
        price = _number(payload.get("price"), None)
        previous = _number(
            payload.get("prev_close", payload.get("previous_close")),
            None,
        )
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
                "is_stale": bool(
                    payload.get("is_stale", payload.get("price_stale", False))
                ),
            }
    except Exception:
        logger.exception("Live analysis snapshot failed for %s", normalized)

    try:
        history = get_chart_history(normalized, period="5d", interval="1d")
        if (
            isinstance(history, pd.DataFrame)
            and not history.empty
            and "Close" in history.columns
        ):
            close = pd.to_numeric(history["Close"], errors="coerce").dropna()
            if not close.empty:
                price = float(close.iloc[-1])
                previous = float(close.iloc[-2]) if len(close) > 1 else None
                change = (
                    (price / previous - 1.0) * 100.0
                    if previous and previous > 0
                    else None
                )
                attrs = getattr(history, "attrs", {}) or {}
                lineage = attrs.get("data_lineage") or {}
                return {
                    "price": price,
                    "change": change,
                    "source": str(
                        lineage.get("source")
                        or attrs.get("source")
                        or "history"
                    ),
                    "fetched_at": str(lineage.get("fetched_at") or "—"),
                    "is_stale": bool(lineage.get("is_stale", False)),
                }
    except Exception:
        logger.exception("Analysis history quote fallback failed for %s", normalized)
    return {
        "price": None,
        "change": None,
        "source": "غير متاح",
        "fetched_at": "—",
        "is_stale": True,
    }


def _company_meta(symbol: str) -> tuple[str, str]:
    try:
        info = _company_details(symbol)
        if isinstance(info, dict):
            return (
                str(info.get("name") or info.get("Name") or symbol),
                str(info.get("sector") or info.get("Sector") or ""),
            )
        if isinstance(info, (list, tuple)):
            name = str(info[0] or symbol) if info else symbol
            sector = str(info[1] or "") if len(info) > 1 else ""
            return name, sector
        if info:
            return str(info), ""
    except Exception:
        logger.exception("Company metadata failed for %s", symbol)
    return symbol, ""


def _watchlist() -> pd.DataFrame:
    try:
        value = fetch_table("watchlist")
        return value if isinstance(value, pd.DataFrame) else pd.DataFrame()
    except Exception:
        logger.exception("Analysis watchlist load failed")
        return pd.DataFrame()


def _symbol_universe(
    trades: pd.DataFrame,
    watchlist: pd.DataFrame,
) -> list[str]:
    values: list[str] = []
    if not trades.empty and "symbol" in trades.columns:
        values.extend(trades["symbol"].dropna().astype(str).tolist())
    if not watchlist.empty and "symbol" in watchlist.columns:
        values.extend(watchlist["symbol"].dropna().astype(str).tolist())
    return clean_symbols(values)


def _open_positions(symbol: str, trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "symbol" not in trades.columns:
        return pd.DataFrame()
    normalized = trades["symbol"].fillna("").astype(str).map(normalize_symbol)
    status = safe_status_series(trades)
    return trades[(normalized == symbol) & (status == "open")]


def _render_watchlist_action(symbol: str, watchlist: pd.DataFrame) -> None:
    try:
        existing = set()
        if not watchlist.empty and "symbol" in watchlist.columns:
            existing = {
                normalize_symbol(value)
                for value in watchlist["symbol"].dropna().astype(str)
            }
        if symbol in existing:
            if st.button(
                "إزالة من المراقبة",
                use_container_width=True,
                key=f"analysis_watch_remove:{symbol}",
            ):
                if execute_query(
                    "DELETE FROM watchlist WHERE symbol=%s",
                    (symbol,),
                ):
                    st.success("تمت الإزالة من قائمة المراقبة")
                    st.cache_data.clear()
                    st.rerun()
                st.error("تعذر إزالة الرمز")
            return
        if st.button(
            "إضافة للمراقبة",
            use_container_width=True,
            key=f"analysis_watch_add:{symbol}",
        ):
            saved = execute_query(
                "INSERT INTO watchlist (symbol, created_at) "
                "VALUES (%s,CURRENT_TIMESTAMP) "
                "ON CONFLICT (symbol) DO NOTHING",
                (symbol,),
            )
            if saved:
                st.success("تمت الإضافة إلى قائمة المراقبة")
                st.cache_data.clear()
                st.rerun()
            st.info("الرمز موجود مسبقًا أو تعذر حفظه")
    except Exception:
        logger.exception("Analysis watchlist action failed")
        st.warning("تعذر تحديث قائمة المراقبة، والتحليل ما زال متاحًا.")


def _render_header(
    symbol: str,
    name: str,
    sector: str,
    trades: pd.DataFrame,
    watchlist: pd.DataFrame,
    interval: str,
) -> None:
    try:
        snapshot = _price_snapshot(symbol)
    except Exception:
        logger.exception("Analysis header quote failed")
        snapshot = {
            "price": None,
            "change": None,
            "source": "غير متاح",
            "fetched_at": "—",
            "is_stale": True,
        }
    price = _number(snapshot.get("price"), None)
    change = _number(snapshot.get("change"), None)
    positions = _open_positions(symbol, trades)

    st.subheader(name or symbol)
    stale = " — السعر قديم" if snapshot.get("is_stale") else ""
    st.caption(
        f"{symbol} — {sector or 'قطاع غير متاح'} — الفاصل {interval} — "
        f"المصدر {snapshot.get('source')} — {snapshot.get('fetched_at')}{stale}"
    )
    c1, c2, c3, c4 = st.columns([1, 1, 1, 0.8])
    c1.metric("السعر الحالي", "—" if price is None else f"{price:,.2f}")
    c2.metric(
        "التغير اليومي",
        "—" if change is None else f"{change:+.2f}%",
    )
    c3.metric("مركز مفتوح", "نعم" if not positions.empty else "لا")
    with c4:
        _render_watchlist_action(symbol, watchlist)


def _run_from_form(symbol: str, interval: str) -> bool:
    from .workspace_v20 import _generate

    with st.spinner("جاري تحليل الاتجاه والخطة والمخاطر..."):
        payload = _generate(symbol, interval, refresh=True)
    report = payload.get("report") if isinstance(payload, dict) else None
    return isinstance(report, dict) and bool(report)


def view_analysis(fin: dict[str, Any] | None) -> None:
    """Render the only comprehensive-analysis page used by the application."""
    finance = fin if isinstance(fin, dict) else {}
    trades = finance.get("all_trades")
    if not isinstance(trades, pd.DataFrame):
        trades = pd.DataFrame()
    watchlist = _watchlist()
    universe = _symbol_universe(trades, watchlist)

    st.header("📊 التحليل الشامل")
    st.caption(
        "اختر الرمز والفاصل؛ يعرض النظام الصعود والهبوط والدخول والوقف "
        "والأهداف ورأي المستشار في الصفحة نفسها."
    )

    current_symbol = normalize_symbol(
        st.session_state.get("analysis_active_symbol")
    )
    current_interval = str(
        st.session_state.get("analysis_active_interval") or "1d"
    )
    current_label = next(
        (
            label
            for label, value in TIMEFRAME_OPTIONS.items()
            if value == current_interval
        ),
        "يومي",
    )

    with st.form("analysis_symbol_form"):
        c1, c2, c3 = st.columns([2.2, 1.2, 0.8])
        raw_symbol = c1.text_input(
            "رمز السهم أو الأصل",
            value=current_symbol,
            placeholder="مثال: 2222 أو AAPL أو BTCUSD",
        )
        timeframe_label = c2.selectbox(
            "الفاصل",
            options=list(TIMEFRAME_OPTIONS),
            index=list(TIMEFRAME_OPTIONS).index(current_label),
        )
        submitted = c3.form_submit_button(
            "تحليل",
            type="primary",
            use_container_width=True,
        )

    if universe:
        st.caption("رموزك السريعة: " + "، ".join(universe[:8]))

    if submitted:
        symbol = normalize_symbol(raw_symbol)
        if not symbol or symbol == ".SR":
            st.error("أدخل رمزًا صحيحًا مثل 2222 أو AAPL أو BTCUSD")
        else:
            interval = TIMEFRAME_OPTIONS[timeframe_label]
            st.session_state["analysis_active_symbol"] = symbol
            st.session_state["analysis_active_interval"] = interval
            try:
                _run_from_form(symbol, interval)
            except Exception:
                logger.exception("Analysis form execution failed")
            st.rerun()

    symbol = normalize_symbol(
        st.session_state.get("analysis_active_symbol")
    )
    interval = str(
        st.session_state.get("analysis_active_interval") or "1d"
    )
    if not symbol or symbol == ".SR":
        st.info("اكتب الرمز واختر الفاصل ثم اضغط «تحليل».")
        return

    name, sector = _company_meta(symbol)
    try:
        _render_header(symbol, name, sector, trades, watchlist, interval)
    except Exception:
        logger.exception("Analysis header presentation failed")
        st.subheader(name or symbol)
        st.caption(f"{symbol} — الفاصل {interval}")

    try:
        from .workspace_v20 import render_decision_workspace

        render_decision_workspace(symbol, interval, finance)
    except Exception:
        logger.exception("Comprehensive analysis workspace failed")
        st.error("تعذر تشغيل التحليل الشامل الآن.")
        st.caption("رمز التشخيص: analysis_workspace")


__all__ = ["TIMEFRAME_OPTIONS", "view_analysis"]
