"""Owned-stock summary embedded in the main dashboard.

The table is intentionally database-backed.  Normal page navigation never calls
market providers; prices and previous closes come from the latest explicit
portfolio refresh performed from Settings.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
import streamlit as st

from components import render_kpi, safe_fmt
from views.shared import _normalize_symbol, _safe_status_series


def _number_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _first_text(frame: pd.DataFrame, *columns: str, default: str = "") -> str:
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].dropna().astype(str).str.strip()
        values = values[(values != "") & (values.str.lower() != "nan")]
        if not values.empty:
            return str(values.iloc[0])
    return default


def _portfolio_label(frame: pd.DataFrame) -> str:
    if "strategy" not in frame.columns:
        return "أسهم"
    strategies = " | ".join(frame["strategy"].dropna().astype(str).tolist())
    has_speculation = "مضارب" in strategies
    has_investment = "استثمار" in strategies
    if has_speculation and has_investment:
        return "مضاربة + استثمار"
    if has_speculation:
        return "مضاربة"
    if has_investment:
        return "استثمار"
    return "أسهم"


def _open_stock_positions(finance: dict[str, Any]) -> pd.DataFrame:
    positions = finance.get("open_positions_df")
    if not isinstance(positions, pd.DataFrame):
        positions = finance.get("all_trades")
    if not isinstance(positions, pd.DataFrame) or positions.empty:
        return pd.DataFrame()

    frame = positions.copy()
    if "status" in frame.columns:
        status = _safe_status_series(frame)
        if len(status):
            frame = frame[status == "open"].copy()
    if frame.empty:
        return frame

    if "asset_type" in frame.columns:
        asset_type = frame["asset_type"].astype(str).str.strip().str.lower()
        frame = frame[~asset_type.eq("sukuk")].copy()
    if frame.empty:
        return frame

    if "symbol" not in frame.columns:
        return pd.DataFrame()
    frame["symbol"] = frame["symbol"].astype(str).map(_normalize_symbol)
    frame = frame[
        frame["symbol"].astype(str).str.strip().ne("")
        & frame["symbol"].astype(str).str.lower().ne("nan")
    ].copy()
    return frame


def build_owned_stocks_frame(finance: dict[str, Any] | None) -> pd.DataFrame:
    """Aggregate multiple open lots into one technically useful row per symbol."""
    source = _open_stock_positions(finance or {})
    columns = [
        "company_name",
        "symbol",
        "portfolio",
        "quantity",
        "average_cost",
        "current_price",
        "day_change_amount",
        "day_change_pct",
        "daily_pnl",
        "market_value",
        "unrealized_pnl",
        "return_pct",
        "direction",
        "price_source",
        "price_stale",
        "price_fetched_at",
    ]
    if source.empty:
        return pd.DataFrame(columns=columns)

    source["quantity"] = _number_series(source, "quantity")
    source["entry_price"] = _number_series(source, "entry_price")
    source["current_price"] = _number_series(source, "current_price")
    source["prev_close"] = _number_series(source, "prev_close")

    records: list[dict[str, Any]] = []
    for symbol, group in source.groupby("symbol", sort=True, dropna=False):
        quantity = float(group["quantity"].sum())
        if quantity <= 0:
            continue

        total_cost = float((group["quantity"] * group["entry_price"]).sum())
        market_value = float((group["quantity"] * group["current_price"]).sum())
        average_cost = total_cost / quantity if quantity else 0.0
        current_price = market_value / quantity if quantity else 0.0
        unrealized = market_value - total_cost
        return_pct = unrealized / total_cost * 100 if total_cost > 0 else math.nan

        previous = group["prev_close"]
        day_available = bool((previous > 0).all()) and current_price > 0
        if day_available:
            previous_value = float((group["quantity"] * previous).sum())
            previous_price = previous_value / quantity if quantity else 0.0
            day_change_amount = current_price - previous_price
            day_change_pct = (
                day_change_amount / previous_price * 100 if previous_price > 0 else math.nan
            )
            daily_pnl = market_value - previous_value
            direction = (
                "صاعد"
                if day_change_amount > 0
                else "هابط"
                if day_change_amount < 0
                else "مستقر"
            )
        else:
            day_change_amount = math.nan
            day_change_pct = math.nan
            daily_pnl = math.nan
            direction = "غير متاح"

        stale = True
        if "price_stale" in group.columns:
            stale = bool(group["price_stale"].fillna(True).astype(bool).any())

        records.append(
            {
                "company_name": _first_text(
                    group,
                    "company_name",
                    "name",
                    default=str(symbol),
                ),
                "symbol": str(symbol),
                "portfolio": _portfolio_label(group),
                "quantity": quantity,
                "average_cost": average_cost,
                "current_price": current_price,
                "day_change_amount": day_change_amount,
                "day_change_pct": day_change_pct,
                "daily_pnl": daily_pnl,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "return_pct": return_pct,
                "direction": direction,
                "price_source": _first_text(
                    group,
                    "price_source",
                    default="محفوظ",
                ),
                "price_stale": stale,
                "price_fetched_at": _first_text(
                    group,
                    "price_fetched_at",
                    default="—",
                ),
            }
        )

    frame = pd.DataFrame(records, columns=columns)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["market_value", "symbol"],
        ascending=[False, True],
        ignore_index=True,
    )


def _render_owned_summary(frame: pd.DataFrame) -> None:
    market_value = float(frame["market_value"].sum())
    unrealized = float(frame["unrealized_pnl"].sum())
    daily_values = pd.to_numeric(frame["daily_pnl"], errors="coerce")
    daily_pnl = float(daily_values.dropna().sum()) if daily_values.notna().any() else math.nan

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("عدد الأسهم", f"{len(frame)}", "neutral", "📌")
    with c2:
        render_kpi("القيمة السوقية", safe_fmt(market_value), "blue", "📊")
    with c3:
        render_kpi(
            "تغير اليوم",
            "—" if math.isnan(daily_pnl) else safe_fmt(daily_pnl),
            "neutral"
            if math.isnan(daily_pnl)
            else "success"
            if daily_pnl >= 0
            else "danger",
            "↕️",
        )
    with c4:
        render_kpi(
            "الربح غير المحقق",
            safe_fmt(unrealized),
            "success" if unrealized >= 0 else "danger",
            "💹",
        )


def _display_table(frame: pd.DataFrame) -> None:
    display = frame[
        [
            "company_name",
            "symbol",
            "portfolio",
            "quantity",
            "average_cost",
            "current_price",
            "day_change_amount",
            "day_change_pct",
            "daily_pnl",
            "market_value",
            "unrealized_pnl",
            "return_pct",
            "direction",
        ]
    ].rename(
        columns={
            "company_name": "اسم السهم",
            "symbol": "الرمز",
            "portfolio": "المحفظة",
            "quantity": "الكمية",
            "average_cost": "متوسط التكلفة",
            "current_price": "السعر الحالي",
            "day_change_amount": "تغير السعر اليومي",
            "day_change_pct": "التغير %",
            "daily_pnl": "أثر اليوم",
            "market_value": "القيمة السوقية",
            "unrealized_pnl": "الربح/الخسارة",
            "return_pct": "العائد %",
            "direction": "اتجاه اليوم",
        }
    )

    height = min(480, max(170, 39 * (len(display) + 1)))
    st.dataframe(
        display,
        width="stretch",
        height=height,
        hide_index=True,
        column_config={
            "الكمية": st.column_config.NumberColumn(format="%.2f"),
            "متوسط التكلفة": st.column_config.NumberColumn(format="%.2f ر.س"),
            "السعر الحالي": st.column_config.NumberColumn(format="%.2f ر.س"),
            "تغير السعر اليومي": st.column_config.NumberColumn(format="%+.2f ر.س"),
            "التغير %": st.column_config.NumberColumn(format="%+.2f%%"),
            "أثر اليوم": st.column_config.NumberColumn(format="%+.2f ر.س"),
            "القيمة السوقية": st.column_config.NumberColumn(format="%.2f ر.س"),
            "الربح/الخسارة": st.column_config.NumberColumn(format="%+.2f ر.س"),
            "العائد %": st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )


def render_owned_stocks(finance: dict[str, Any] | None) -> None:
    """Render the former pulse page as a compact dropdown on the home page."""
    open_once = bool(st.session_state.pop("_owned_stocks_open_once", False))
    with st.expander("📋 أسهمي المملوكة", expanded=open_once):
        st.caption(
            "ملخص موحد للمراكز المفتوحة في المضاربة والاستثمار. "
            "الأسعار والتغير اليومي يعتمدان آخر تحديث محفوظ، ولا يتم الاتصال "
            "بمصادر السوق تلقائيًا عند فتح الرئيسية."
        )
        frame = build_owned_stocks_frame(finance)
        if frame.empty:
            st.info("لا توجد أسهم مفتوحة حاليًا؛ الصكوك تظهر داخل مركز المحافظ.")
            return

        _render_owned_summary(frame)
        _display_table(frame)

        stale_count = int(frame["price_stale"].fillna(True).astype(bool).sum())
        unavailable = int(frame["day_change_pct"].isna().sum())
        notes = []
        if stale_count:
            notes.append(f"{stale_count} سهم يعتمد آخر سعر محفوظ")
        if unavailable:
            notes.append(f"التغير اليومي غير متاح لعدد {unavailable} سهم")
        if notes:
            st.warning(" — ".join(notes))

        if st.button(
            "فتح الإعدادات لتحديث الأسعار",
            icon="🔄",
            use_container_width=True,
            key="owned_stocks_open_settings",
        ):
            from views.navbar import navigate_to

            navigate_to("settings")
