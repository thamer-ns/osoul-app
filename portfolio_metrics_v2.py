"""Unified portfolio accounting for Osoli.

The legacy dashboard and portfolio pages calculated overlapping metrics through
separate paths. This module provides one tenant-aware source of truth for cash,
positions, realised/unrealised profit, price quality and XIRR.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict

import pandas as pd
import streamlit as st

logger = logging.getLogger("osoli.portfolio_metrics")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else float(default)
    except Exception:
        return float(default)


def _frame(value: Any) -> pd.DataFrame:
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _normalise_dates(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in ("date", "exit_date", "created_at", "updated_at"):
        if column in output.columns:
            output[column] = pd.to_datetime(
                output[column],
                errors="coerce",
                utc=True,
            ).dt.tz_convert(None)
    return output


def _normalise_status(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=str)
    status = frame.get(
        "status",
        pd.Series("Open", index=frame.index),
    ).astype(str).str.strip().str.lower()
    exit_price = pd.to_numeric(
        frame.get("exit_price", pd.Series(0.0, index=frame.index)),
        errors="coerce",
    ).fillna(0.0)
    closed = status.isin(
        {
            "close",
            "closed",
            "sold",
            "sell",
            "مغلق",
            "مغلقة",
            "تم البيع",
            "بيع",
        }
    ) | exit_price.gt(0)
    return pd.Series(
        ["Close" if value else "Open" for value in closed],
        index=frame.index,
    )


def _sum_amount(frame: pd.DataFrame) -> float:
    if frame.empty or "amount" not in frame.columns:
        return 0.0
    return float(
        pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0).sum()
    )


def _live_prices(open_positions: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    if open_positions.empty or "symbol" not in open_positions.columns:
        return {}
    try:
        from market_data import fetch_batch_data, get_ticker_symbol

        symbols = []
        for raw in open_positions["symbol"].dropna().astype(str):
            symbol = get_ticker_symbol(raw)
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        return fetch_batch_data(symbols) if symbols else {}
    except Exception:
        logger.exception("live price batch failed")
        return {}


def _apply_market_prices(open_positions: pd.DataFrame) -> pd.DataFrame:
    if open_positions.empty:
        return open_positions
    frame = open_positions.copy()
    live = _live_prices(frame)
    try:
        from market_data import get_ticker_symbol
    except Exception:
        get_ticker_symbol = lambda value: str(value or "").strip().upper()

    prices = []
    previous = []
    sources = []
    stale = []
    for _, row in frame.iterrows():
        symbol = get_ticker_symbol(row.get("symbol"))
        asset_type = str(row.get("asset_type") or "Stock").strip().lower()
        stored = _number(
            row.get("current_price"),
            _number(row.get("entry_price")),
        )
        if asset_type == "sukuk":
            price = _number(row.get("entry_price"), stored)
            payload = {"source": "book_value", "prev_close": 0.0}
        else:
            payload = (
                live.get(symbol)
                or live.get(str(symbol).upper())
                or {}
            )
            price = _number(payload.get("price"), stored)
            if price <= 0:
                price = stored
        prices.append(price)
        previous.append(_number(payload.get("prev_close"), 0.0))
        sources.append(str(payload.get("source") or "stored"))
        stale.append(bool(payload.get("is_stale", price <= 0)))

    frame["current_price"] = prices
    frame["prev_close"] = previous
    frame["price_source"] = sources
    frame["price_stale"] = stale
    frame["day_change"] = (
        (frame["current_price"] - frame["prev_close"])
        .div(frame["prev_close"].replace(0, pd.NA))
        .mul(100)
    )
    return frame


def _empty_result() -> Dict[str, Any]:
    return {
        "cost_open": 0.0,
        "market_val_open": 0.0,
        "cash": 0.0,
        "unrealized_pl": 0.0,
        "realized_pl": 0.0,
        "total_deposited": 0.0,
        "total_withdrawn": 0.0,
        "total_returns": 0.0,
        "deposits": pd.DataFrame(),
        "withdrawals": pd.DataFrame(),
        "returns": pd.DataFrame(),
        "all_trades": pd.DataFrame(),
        "open_positions_df": pd.DataFrame(),
        "closed_positions_df": pd.DataFrame(),
        "portfolio_value": 0.0,
        "cash_pct": 0.0,
        "xirr": None,
        "xirr_note": "",
        "data_quality": {"ok": True, "notes": []},
    }


@st.cache_data(ttl=120, show_spinner=False)
def calculate_portfolio_metrics_v2(
    include_xirr: bool = True,
    cache_key: str = "",
) -> Dict[str, Any]:
    """Return a consistent portfolio snapshot for the active tenant.

    ``cache_key`` must include user and portfolio identity; the router supplies
    that key so Streamlit's process-wide cache cannot cross user boundaries.
    """
    del cache_key
    result = _empty_result()
    try:
        from analytics_hardening import compute_portfolio_xirr
        from database import fetch_table

        trades = _normalise_dates(_frame(fetch_table("trades")))
        deposits = _normalise_dates(_frame(fetch_table("deposits")))
        withdrawals = _normalise_dates(_frame(fetch_table("withdrawals")))
        returns = _normalise_dates(_frame(fetch_table("returnsgrants")))

        deposited = _sum_amount(deposits)
        withdrawn = _sum_amount(withdrawals)
        distributed = _sum_amount(returns)

        result.update(
            {
                "total_deposited": deposited,
                "total_withdrawn": withdrawn,
                "total_returns": distributed,
                "deposits": deposits,
                "withdrawals": withdrawals,
                "returns": returns,
            }
        )

        if trades.empty:
            cash = deposited + distributed - withdrawn
            result.update(
                {
                    "cash": cash,
                    "portfolio_value": cash,
                    "cash_pct": 100.0 if cash > 0 else 0.0,
                }
            )
            if include_xirr:
                rate, note = compute_portfolio_xirr(
                    deposits,
                    withdrawals,
                    returns,
                    ending_value=cash,
                )
                result["xirr"] = rate
                result["xirr_note"] = note
            return result

        for column in (
            "quantity",
            "entry_price",
            "exit_price",
            "current_price",
        ):
            if column not in trades.columns:
                trades[column] = 0.0
            trades[column] = pd.to_numeric(
                trades[column],
                errors="coerce",
            ).fillna(0.0)

        trades["status"] = _normalise_status(trades)
        trades["total_cost"] = trades["quantity"] * trades["entry_price"]
        closed = trades[trades["status"].eq("Close")].copy()
        open_positions = trades[trades["status"].eq("Open")].copy()
        open_positions = _apply_market_prices(open_positions)

        closed["current_price"] = closed["exit_price"]
        closed["proceeds"] = closed["quantity"] * closed["exit_price"]
        closed["market_value"] = closed["proceeds"]
        closed["gain"] = closed["proceeds"] - closed["total_cost"]
        closed["gain_pct"] = (
            closed["gain"]
            .div(closed["total_cost"].replace(0, pd.NA))
            .mul(100)
            .fillna(0.0)
        )

        open_positions["market_value"] = (
            open_positions["quantity"] * open_positions["current_price"]
        )
        open_positions["gain"] = (
            open_positions["market_value"] - open_positions["total_cost"]
        )
        open_positions["gain_pct"] = (
            open_positions["gain"]
            .div(open_positions["total_cost"].replace(0, pd.NA))
            .mul(100)
            .fillna(0.0)
        )

        all_trades = pd.concat(
            [open_positions, closed],
            ignore_index=True,
            sort=False,
        )
        purchase_cost = float(trades["total_cost"].sum())
        sale_proceeds = float(closed["proceeds"].sum())
        cash = (
            deposited
            + distributed
            + sale_proceeds
            - withdrawn
            - purchase_cost
        )
        open_cost = float(open_positions["total_cost"].sum())
        open_market = float(open_positions["market_value"].sum())
        unrealised = float(open_positions["gain"].sum())
        realised = float(closed["gain"].sum())
        portfolio_value = cash + open_market
        cash_pct = cash / portfolio_value * 100 if portfolio_value > 0 else 0.0

        notes = []
        if cash < -0.01:
            notes.append("السيولة سالبة؛ راجع الإيداعات أو عمليات الشراء المسجلة")
        missing_exit = closed["exit_price"].le(0)
        if bool(missing_exit.any()):
            notes.append("توجد صفقات مغلقة دون سعر بيع صالح")
        stale_count = int(
            open_positions.get("price_stale", pd.Series(dtype=bool))
            .fillna(False)
            .sum()
        )
        if stale_count:
            notes.append(f"يوجد {stale_count} مركز بسعر احتياطي أو قديم")

        result.update(
            {
                "cost_open": open_cost,
                "market_val_open": open_market,
                "cash": cash,
                "unrealized_pl": unrealised,
                "realized_pl": realised,
                "all_trades": all_trades,
                "open_positions_df": open_positions,
                "closed_positions_df": closed,
                "portfolio_value": portfolio_value,
                "cash_pct": cash_pct,
                "data_quality": {"ok": not notes, "notes": notes},
            }
        )

        if include_xirr:
            rate, note = compute_portfolio_xirr(
                deposits,
                withdrawals,
                returns,
                ending_value=portfolio_value,
            )
            result["xirr"] = rate
            result["xirr_note"] = note
        return result
    except Exception:
        logger.exception("portfolio metrics calculation failed")
        result["data_quality"] = {
            "ok": False,
            "notes": ["تعذر حساب ملخص المحفظة"],
        }
        return result


def install_portfolio_metrics_v2() -> None:
    import analytics

    analytics.calculate_portfolio_metrics = calculate_portfolio_metrics_v2
