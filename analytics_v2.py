"""User-scoped portfolio analytics for Osoli v2."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from market_data_v2 import fetch_batch_data, get_chart_history, get_ticker_symbol
from tenant_db import current_username, fetch_user_table, update_open_price


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _clean_num(df: pd.DataFrame, column: str, default: float = 0.0) -> None:
    if column not in df.columns:
        df[column] = default
    df[column] = pd.to_numeric(df[column], errors="coerce").fillna(default)


def _dates(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], errors="coerce", utc=True).dt.tz_convert(None)
    return out


def _normalize_trade_status(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame() if trades is None else trades.copy()
    out = trades.copy()
    for column in ("status", "exit_price", "exit_date", "asset_type"):
        if column not in out.columns:
            out[column] = None
    status = out["status"].astype(str).str.strip().str.lower()
    exit_price = pd.to_numeric(out["exit_price"], errors="coerce").fillna(0.0)
    exit_date = pd.to_datetime(out["exit_date"], errors="coerce")
    closed_words = {
        "close", "closed", "sold", "sell", "مغلق", "مغلقة", "تم البيع", "بيع",
    }
    is_closed = status.isin(closed_words) | (exit_price > 0) | exit_date.notna()
    out["status"] = np.where(is_closed, "Close", "Open")
    return out


def _table_revision(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "0"
    parts = [str(len(df))]
    for column in ("id", "updated_at", "created_at", "date", "exit_date"):
        if column not in df.columns:
            continue
        if column == "id":
            values = pd.to_numeric(df[column], errors="coerce")
            parts.append(str(values.max() if values.notna().any() else 0))
        else:
            values = pd.to_datetime(df[column], errors="coerce", utc=True)
            mx = values.max()
            parts.append("" if pd.isna(mx) else mx.isoformat())
    return "|".join(parts)


def get_portfolio_cache_key(username: str = "") -> str:
    username = str(username or current_username()).strip()
    frames = [
        fetch_user_table("trades", username),
        fetch_user_table("deposits", username),
        fetch_user_table("withdrawals", username),
        fetch_user_table("returnsgrants", username),
    ]
    return f"{username}::" + "::".join(_table_revision(df) for df in frames)


def _refresh_live_prices(trades: pd.DataFrame, username: str, persist: bool = False) -> pd.DataFrame:
    if trades is None or trades.empty:
        return trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()

    out = trades.copy()
    for column in ("quantity", "entry_price", "current_price", "exit_price", "entry_fees", "exit_fees"):
        _clean_num(out, column, 0.0)

    open_mask = out["status"].astype(str).str.lower().eq("open")
    sukuk_mask = out["asset_type"].astype(str).str.lower().eq("sukuk") if "asset_type" in out.columns else False
    symbols = [
        str(x).strip()
        for x in out.loc[open_mask & ~sukuk_mask, "symbol"].dropna().unique().tolist()
        if str(x).strip()
    ]
    quotes = fetch_batch_data(symbols)

    for idx in out.index[open_mask]:
        symbol = str(out.at[idx, "symbol"] or "").strip()
        if not symbol:
            continue
        if bool(sukuk_mask.loc[idx]) if hasattr(sukuk_mask, "loc") else False:
            out.at[idx, "current_price"] = _num(out.at[idx, "entry_price"])
            continue
        norm = get_ticker_symbol(symbol)
        quote = quotes.get(symbol.upper()) or quotes.get(norm.upper()) or {}
        price = _num(quote.get("price"), 0.0)
        if price <= 0:
            price = _num(out.at[idx, "current_price"], _num(out.at[idx, "entry_price"]))
        if price > 0:
            out.at[idx, "current_price"] = price
            if persist:
                update_open_price(symbol, price, username)
    return out


def _default_result() -> Dict[str, Any]:
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
        "data_quality": {"ok": True, "score": 100, "notes": []},
    }


@st.cache_data(ttl=120, show_spinner=False)
def calculate_portfolio_metrics(include_xirr: bool = True, cache_key: str = "", username: str = "") -> Dict[str, Any]:
    del cache_key
    username = str(username or current_username()).strip()
    result = _default_result()

    trades = fetch_user_table("trades", username)
    deposits = fetch_user_table("deposits", username)
    withdrawals = fetch_user_table("withdrawals", username)
    returns = fetch_user_table("returnsgrants", username)

    trades = _normalize_trade_status(_dates(trades, ("date", "exit_date", "created_at", "updated_at")))
    deposits = _dates(deposits, ("date", "created_at"))
    withdrawals = _dates(withdrawals, ("date", "created_at"))
    returns = _dates(returns, ("date", "created_at"))

    for frame in (deposits, withdrawals, returns):
        if frame is not None and not frame.empty:
            _clean_num(frame, "amount", 0.0)

    total_dep = float(deposits["amount"].sum()) if not deposits.empty else 0.0
    total_wit = float(withdrawals["amount"].sum()) if not withdrawals.empty else 0.0
    total_ret = float(returns["amount"].sum()) if not returns.empty else 0.0

    if trades.empty:
        cash = total_dep + total_ret - total_wit
        result.update(
            total_deposited=total_dep,
            total_withdrawn=total_wit,
            total_returns=total_ret,
            cash=cash,
            portfolio_value=cash,
            cash_pct=100.0 if cash > 0 else 0.0,
            deposits=deposits,
            withdrawals=withdrawals,
            returns=returns,
        )
        if include_xirr:
            result["xirr"], result["xirr_note"] = compute_portfolio_xirr(deposits, withdrawals, returns, ending_value=cash)
        return result

    for column in ("quantity", "entry_price", "exit_price", "current_price", "entry_fees", "exit_fees"):
        _clean_num(trades, column, 0.0)
    if "asset_type" not in trades.columns:
        trades["asset_type"] = "Stock"
    if "symbol" not in trades.columns:
        return result

    trades = _refresh_live_prices(trades, username, persist=False)
    is_closed = trades["status"].eq("Close")
    is_open = ~is_closed

    trades["entry_value"] = trades["quantity"] * trades["entry_price"]
    trades["total_cost"] = trades["entry_value"] + trades["entry_fees"]
    trades["proceeds"] = 0.0
    trades.loc[is_closed, "proceeds"] = (
        trades.loc[is_closed, "quantity"] * trades.loc[is_closed, "exit_price"]
        - trades.loc[is_closed, "exit_fees"]
    )
    trades["market_value"] = 0.0
    trades.loc[is_open, "market_value"] = trades.loc[is_open, "quantity"] * trades.loc[is_open, "current_price"]
    trades.loc[is_closed, "market_value"] = trades.loc[is_closed, "proceeds"]
    trades["gain"] = trades["market_value"] - trades["total_cost"]
    trades["gain_pct"] = np.where(
        trades["total_cost"] > 0,
        trades["gain"] / trades["total_cost"] * 100.0,
        0.0,
    )

    open_trades = trades.loc[is_open].copy()
    closed_trades = trades.loc[is_closed].copy()

    cash = total_dep + total_ret + float(closed_trades["proceeds"].sum()) - total_wit - float(trades["total_cost"].sum())
    market_open = float(open_trades["market_value"].sum())
    portfolio_value = cash + market_open
    notes: List[str] = []

    if cash < -0.01:
        notes.append("الرصيد النقدي سالب؛ راجع الإيداعات وتواريخ الصفقات والرسوم.")
    if (open_trades["current_price"] <= 0).any():
        notes.append("بعض المراكز المفتوحة بلا سعر حالي موثوق.")
    if (closed_trades["exit_price"] <= 0).any():
        notes.append("بعض الصفقات المغلقة بلا سعر بيع صالح.")
    if trades["symbol"].astype(str).str.strip().eq("").any():
        notes.append("توجد صفقات بلا رمز مالي.")

    score = max(0, 100 - 20 * len(notes))
    result.update(
        cost_open=float(open_trades["total_cost"].sum()),
        market_val_open=market_open,
        cash=float(cash),
        unrealized_pl=float(open_trades["gain"].sum()),
        realized_pl=float(closed_trades["gain"].sum()),
        total_deposited=total_dep,
        total_withdrawn=total_wit,
        total_returns=total_ret,
        deposits=deposits,
        withdrawals=withdrawals,
        returns=returns,
        all_trades=trades,
        open_positions_df=open_trades,
        closed_positions_df=closed_trades,
        portfolio_value=float(portfolio_value),
        cash_pct=(float(cash) / portfolio_value * 100.0) if portfolio_value > 0 else 0.0,
        data_quality={"ok": not notes, "score": score, "notes": notes},
    )
    if include_xirr:
        result["xirr"], result["xirr_note"] = compute_portfolio_xirr(deposits, withdrawals, returns, ending_value=portfolio_value)
    return result


def _external_cashflows(deposits: pd.DataFrame, withdrawals: pd.DataFrame, ending_value: float) -> List[Tuple[pd.Timestamp, float]]:
    flows: List[Tuple[pd.Timestamp, float]] = []

    def add(frame: pd.DataFrame, sign: float) -> None:
        if frame is None or frame.empty or "amount" not in frame.columns:
            return
        date_col = "date" if "date" in frame.columns else "created_at"
        if date_col not in frame.columns:
            return
        for _, row in frame.iterrows():
            dt = pd.to_datetime(row.get(date_col), errors="coerce", utc=True)
            amount = _num(row.get("amount"), 0.0) * sign
            if pd.notna(dt) and amount:
                flows.append((pd.Timestamp(dt).tz_convert(None).normalize(), amount))

    add(deposits, -1.0)
    add(withdrawals, +1.0)
    flows.append((pd.Timestamp(datetime.now(timezone.utc)).tz_convert(None).normalize(), float(ending_value)))

    grouped: Dict[pd.Timestamp, float] = {}
    for dt, amount in flows:
        grouped[dt] = grouped.get(dt, 0.0) + amount
    return sorted([(dt, amount) for dt, amount in grouped.items() if abs(amount) > 1e-9], key=lambda item: item[0])


def _xnpv(rate: float, flows: List[Tuple[pd.Timestamp, float]]) -> float:
    if rate <= -0.999999:
        return np.inf
    t0 = flows[0][0]
    return float(sum(amount / ((1.0 + rate) ** (((dt - t0).days) / 365.0)) for dt, amount in flows))


def compute_portfolio_xirr(deposits: pd.DataFrame, withdrawals: pd.DataFrame, returns: pd.DataFrame, ending_value: float) -> Tuple[Optional[float], str]:
    """Money-weighted return using only external cash flows."""
    del returns
    if _num(ending_value) <= 0:
        return None, "القيمة النهائية غير موجبة"
    flows = _external_cashflows(deposits, withdrawals, ending_value)
    amounts = [amount for _, amount in flows]
    if len(flows) < 2 or not any(x < 0 for x in amounts) or not any(x > 0 for x in amounts):
        return None, "تدفقات خارجية غير كافية"

    grid = np.concatenate([np.linspace(-0.95, -0.01, 80), np.linspace(0.0, 2.0, 160), np.linspace(2.1, 10.0, 80)])
    previous_rate = float(grid[0])
    previous_value = _xnpv(previous_rate, flows)
    for rate in grid[1:]:
        value = _xnpv(float(rate), flows)
        if not np.isfinite(value):
            continue
        if value == 0:
            return float(rate), "bracket"
        if np.isfinite(previous_value) and previous_value * value < 0:
            lo, hi = previous_rate, float(rate)
            f_lo = previous_value
            for _ in range(150):
                mid = (lo + hi) / 2.0
                f_mid = _xnpv(mid, flows)
                if abs(f_mid) < 1e-9:
                    return float(mid), "bisect"
                if f_lo * f_mid <= 0:
                    hi = mid
                else:
                    lo, f_lo = mid, f_mid
            return float((lo + hi) / 2.0), "bisect"
        previous_rate, previous_value = float(rate), value
    return None, "لم يتقارب الحساب"


def update_prices(username: str = "") -> bool:
    username = str(username or current_username()).strip()
    trades = _normalize_trade_status(fetch_user_table("trades", username))
    if trades.empty:
        return True
    refreshed = _refresh_live_prices(trades, username, persist=True)
    return not refreshed.empty


def _event_date(value: Any) -> pd.Timestamp:
    dt = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(dt):
        return pd.NaT
    return pd.Timestamp(dt).tz_convert(None).normalize()


@st.cache_data(ttl=600, show_spinner=False)
def compute_portfolio_equity_curve(trades: pd.DataFrame, deposits: pd.DataFrame, withdrawals: pd.DataFrame, returnsgrants: pd.DataFrame, days: int = 365, interval: str = "1d") -> pd.DataFrame:
    """Build daily NAV while preserving positions opened before the chart window."""
    trades = _normalize_trade_status(trades if isinstance(trades, pd.DataFrame) else pd.DataFrame())
    deposits = deposits if isinstance(deposits, pd.DataFrame) else pd.DataFrame()
    withdrawals = withdrawals if isinstance(withdrawals, pd.DataFrame) else pd.DataFrame()
    returnsgrants = returnsgrants if isinstance(returnsgrants, pd.DataFrame) else pd.DataFrame()

    end = pd.Timestamp(datetime.now(timezone.utc).date())
    start = end - pd.Timedelta(days=max(30, int(days)))
    idx = pd.date_range(start=start, end=end, freq="D")
    events: List[Tuple[pd.Timestamp, str, Any]] = []

    def add_cash(frame: pd.DataFrame, sign: float) -> None:
        if frame.empty or "amount" not in frame.columns:
            return
        for _, row in frame.iterrows():
            dt = _event_date(row.get("date", row.get("created_at")))
            amount = _num(row.get("amount")) * sign
            if pd.notna(dt) and amount:
                events.append((dt, "cash", amount))

    add_cash(deposits, +1.0)
    add_cash(withdrawals, -1.0)
    add_cash(returnsgrants, +1.0)

    symbols: set[str] = set()
    for _, row in trades.iterrows():
        symbol = get_ticker_symbol(row.get("symbol"))
        if not symbol:
            continue
        symbols.add(symbol)
        qty = _num(row.get("quantity"))
        entry = _num(row.get("entry_price"))
        entry_fee = _num(row.get("entry_fees"))
        buy_date = _event_date(row.get("date"))
        if pd.notna(buy_date) and qty > 0 and entry > 0:
            events.append((buy_date, "buy", (symbol, qty, entry, entry_fee)))
        if str(row.get("status")).lower() == "close":
            sell_date = _event_date(row.get("exit_date"))
            exit_price = _num(row.get("exit_price"))
            exit_fee = _num(row.get("exit_fees"))
            if pd.notna(sell_date) and qty > 0 and exit_price > 0:
                events.append((sell_date, "sell", (symbol, qty, exit_price, exit_fee)))

    prices: Dict[str, pd.Series] = {}
    for symbol in sorted(symbols):
        try:
            hist = get_chart_history(symbol, years=max(2, int(np.ceil(days / 365)) + 1), interval=interval)
            if hist is None or hist.empty or "Close" not in hist.columns:
                continue
            close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
            close.index = pd.to_datetime(close.index, errors="coerce", utc=True).tz_convert(None).normalize()
            close = close[~close.index.duplicated(keep="last")].sort_index()
            prices[symbol] = close.reindex(idx.union(close.index)).sort_index().ffill().reindex(idx)
        except Exception:
            continue

    events.sort(key=lambda item: item[0])
    cash = 0.0
    positions: Dict[str, float] = {}
    fallback_prices: Dict[str, float] = {}

    def apply_event(kind: str, value: Any) -> None:
        nonlocal cash
        if kind == "cash":
            cash += float(value)
        elif kind == "buy":
            symbol, qty, price, fee = value
            positions[symbol] = positions.get(symbol, 0.0) + qty
            cash -= qty * price + fee
            fallback_prices[symbol] = price
        elif kind == "sell":
            symbol, qty, price, fee = value
            positions[symbol] = positions.get(symbol, 0.0) - qty
            if positions[symbol] <= 1e-9:
                positions.pop(symbol, None)
            cash += qty * price - fee
            fallback_prices[symbol] = price

    pointer = 0
    while pointer < len(events) and events[pointer][0] < start:
        _, kind, value = events[pointer]
        apply_event(kind, value)
        pointer += 1

    rows: List[Dict[str, Any]] = []
    for day in idx:
        while pointer < len(events) and events[pointer][0] <= day:
            _, kind, value = events[pointer]
            apply_event(kind, value)
            pointer += 1

        holdings = 0.0
        missing_prices = 0
        for symbol, qty in positions.items():
            series = prices.get(symbol)
            price = np.nan
            if series is not None and day in series.index:
                price = series.loc[day]
            if pd.isna(price):
                price = fallback_prices.get(symbol, 0.0)
                missing_prices += 1
            holdings += qty * _num(price)

        equity = cash + holdings
        rows.append({"date": day, "cash": cash, "holdings": holdings, "equity": equity, "missing_prices": missing_prices})

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["net_external_flow"] = 0.0
    out["return"] = out["equity"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out["growth_index"] = (1.0 + out["return"]).cumprod() * 100.0
    return out


def generate_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty or "date" not in trades.columns:
        return pd.DataFrame()
    out = trades.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in ("quantity", "entry_price", "entry_fees"):
        _clean_num(out, col, 0.0)
    out["net_invested"] = out["quantity"] * out["entry_price"] + out["entry_fees"]
    return out.sort_values("date")[["date", "net_invested"]]
