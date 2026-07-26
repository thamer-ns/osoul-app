"""Corrected portfolio return and NAV calculations installed at runtime.

The legacy application counted internal distributions twice in XIRR and showed
cumulative purchases as portfolio growth. This module keeps the public
``analytics`` API but replaces those calculations with money-flow aware
implementations.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


def _to_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else float(default)
    except Exception:
        return float(default)


def _external_cashflows(
    deposits: pd.DataFrame,
    withdrawals: pd.DataFrame,
    returnsgrants: pd.DataFrame,
    ending_value: float,
) -> List[Tuple[pd.Timestamp, float]]:
    flows: list[tuple[pd.Timestamp, float]] = []

    def add_rows(df: pd.DataFrame, sign: float, *, external_only: bool = False) -> None:
        if df is None or df.empty or "amount" not in df.columns:
            return
        date_col = "date" if "date" in df.columns else "created_at" if "created_at" in df.columns else None
        if not date_col:
            return
        tmp = df.copy()
        tmp[date_col] = _to_dates(tmp[date_col])
        tmp["amount"] = pd.to_numeric(tmp["amount"], errors="coerce")
        for _, row in tmp.iterrows():
            if external_only:
                flag = str(row.get("is_external", row.get("flow_type", ""))).strip().lower()
                if flag not in {"1", "true", "yes", "external", "withdrawn", "خارجية", "مسحوب"}:
                    continue
            dt = row.get(date_col)
            amount = row.get("amount")
            if pd.isna(dt) or pd.isna(amount) or float(amount) == 0:
                continue
            flows.append((pd.Timestamp(dt).normalize(), float(amount) * sign))

    add_rows(deposits, -1.0)
    add_rows(withdrawals, +1.0)
    add_rows(returnsgrants, +1.0, external_only=True)

    end_date = pd.Timestamp(datetime.now(timezone.utc)).tz_convert(None).normalize()
    if ending_value > 0:
        flows.append((end_date, float(ending_value)))

    grouped: dict[pd.Timestamp, float] = {}
    for dt, amount in flows:
        grouped[dt] = grouped.get(dt, 0.0) + amount
    return sorted(
        [(dt, amount) for dt, amount in grouped.items() if abs(amount) > 1e-9],
        key=lambda x: x[0],
    )


def _xnpv(rate: float, flows: Iterable[Tuple[pd.Timestamp, float]]) -> float:
    if rate <= -0.999999999:
        return math.inf
    flows = list(flows)
    if not flows:
        return math.nan
    t0 = flows[0][0]
    return float(
        sum(amount / ((1.0 + rate) ** (((dt - t0).days) / 365.0)) for dt, amount in flows)
    )


def _solve_xirr(flows: List[Tuple[pd.Timestamp, float]]) -> Optional[float]:
    if len(flows) < 2:
        return None
    amounts = [amount for _, amount in flows]
    if not (any(x < 0 for x in amounts) and any(x > 0 for x in amounts)):
        return None

    grid = np.unique(
        np.concatenate(
            [
                np.linspace(-0.999, 1.0, 250),
                np.geomspace(2.01, 1001.0, 240) - 1.0,
            ]
        )
    )
    previous_rate = float(grid[0])
    previous_value = _xnpv(previous_rate, flows)
    for rate_raw in grid[1:]:
        rate = float(rate_raw)
        value = _xnpv(rate, flows)
        if not (math.isfinite(previous_value) and math.isfinite(value)):
            previous_rate, previous_value = rate, value
            continue
        if value == 0:
            return rate
        if previous_value == 0:
            return previous_rate
        if previous_value * value < 0:
            lo, hi = previous_rate, rate
            flo = previous_value
            for _ in range(160):
                mid = (lo + hi) / 2.0
                fmid = _xnpv(mid, flows)
                if not math.isfinite(fmid):
                    return None
                if abs(fmid) < 1e-10 or abs(hi - lo) < 1e-10:
                    return float(mid)
                if flo * fmid <= 0:
                    hi = mid
                else:
                    lo, flo = mid, fmid
            return float((lo + hi) / 2.0)
        previous_rate, previous_value = rate, value
    return None


def compute_portfolio_xirr(
    dep: pd.DataFrame,
    wit: pd.DataFrame,
    ret: pd.DataFrame,
    ending_value: float,
):
    ending_value = _safe_float(ending_value)
    if ending_value <= 0:
        return None, "ending_value<=0"
    flows = _external_cashflows(dep, wit, ret, ending_value)
    rate = _solve_xirr(flows)
    return (rate, "cashflow_bisection_v2") if rate is not None else (None, "no_convergence")


def _normalise_status(value: object) -> str:
    text = str(value or "").strip().lower()
    return "closed" if text in {"close", "closed", "sold", "sell", "مغلق", "مغلقة", "تم البيع"} else "open"


def _event_date(value: object) -> pd.Timestamp:
    result = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(result):
        return pd.NaT
    return pd.Timestamp(result).tz_convert(None).normalize()


def compute_portfolio_equity_curve(
    trades: pd.DataFrame,
    deposits: pd.DataFrame,
    withdrawals: pd.DataFrame,
    returnsgrants: pd.DataFrame,
    days: int = 365,
    interval: str = "1d",
) -> pd.DataFrame:
    """Reconstruct daily NAV and time-weighted return without look-ahead.

    Events before the requested window are processed into the opening cash and
    position state. Deposits and withdrawals are external flows; distributions
    are internal portfolio income unless explicitly withdrawn.
    """
    try:
        from market_data import get_chart_history, get_ticker_symbol
    except Exception:
        return pd.DataFrame()

    trades = trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    deposits = deposits.copy() if isinstance(deposits, pd.DataFrame) else pd.DataFrame()
    withdrawals = withdrawals.copy() if isinstance(withdrawals, pd.DataFrame) else pd.DataFrame()
    returnsgrants = returnsgrants.copy() if isinstance(returnsgrants, pd.DataFrame) else pd.DataFrame()

    end = pd.Timestamp(datetime.now(timezone.utc)).tz_convert(None).normalize()
    start = end - pd.Timedelta(days=max(30, int(days or 365)))
    index = pd.date_range(start=start, end=end, freq="D")
    if index.empty:
        return pd.DataFrame()

    events: list[tuple[pd.Timestamp, str, object]] = []

    def cash_events(df: pd.DataFrame, sign: float, external: bool) -> None:
        if df.empty or "amount" not in df.columns:
            return
        dcol = "date" if "date" in df.columns else "created_at" if "created_at" in df.columns else None
        if not dcol:
            return
        for _, row in df.iterrows():
            dt = _event_date(row.get(dcol))
            amount = _safe_float(row.get("amount"), math.nan)
            if pd.isna(dt) or not math.isfinite(amount) or amount == 0:
                continue
            events.append((dt, "external_cash" if external else "internal_cash", sign * amount))

    cash_events(deposits, +1.0, True)
    cash_events(withdrawals, -1.0, True)
    cash_events(returnsgrants, +1.0, False)

    symbols: set[str] = set()
    if not trades.empty:
        for _, row in trades.iterrows():
            symbol = get_ticker_symbol(row.get("symbol"))
            qty = _safe_float(row.get("quantity"), math.nan)
            entry = _safe_float(row.get("entry_price"), math.nan)
            buy_date = _event_date(row.get("date"))
            if symbol and math.isfinite(qty) and qty > 0 and math.isfinite(entry) and entry > 0 and not pd.isna(buy_date):
                symbols.add(symbol)
                events.append((buy_date, "buy", (symbol, qty, entry)))
            if _normalise_status(row.get("status")) == "closed":
                exit_price = _safe_float(row.get("exit_price"), math.nan)
                exit_date = _event_date(row.get("exit_date"))
                if symbol and math.isfinite(qty) and qty > 0 and math.isfinite(exit_price) and exit_price > 0 and not pd.isna(exit_date):
                    events.append((exit_date, "sell", (symbol, qty, exit_price)))

    histories: dict[str, pd.Series] = {}
    earliest = min((event[0] for event in events), default=start)
    years = max(1, int(math.ceil((end - min(start, earliest)).days / 365.0)) + 1)
    for symbol in sorted(symbols):
        try:
            history = get_chart_history(symbol, years=years, interval=interval)
            if not isinstance(history, pd.DataFrame) or history.empty or "Close" not in history.columns:
                continue
            close = pd.to_numeric(history["Close"], errors="coerce").dropna()
            close.index = pd.to_datetime(close.index, errors="coerce", utc=True).tz_convert(None).normalize()
            close = close[~close.index.duplicated(keep="last")].sort_index()
            histories[symbol] = close.reindex(index, method="ffill")
        except Exception:
            continue

    events.sort(key=lambda item: item[0])
    by_day: dict[pd.Timestamp, list[tuple[str, object]]] = {}
    for dt, event_type, value in events:
        by_day.setdefault(dt, []).append((event_type, value))

    cash = 0.0
    positions: dict[str, float] = {}
    last_price: dict[str, float] = {}
    rows: list[dict] = []
    previous_equity: Optional[float] = None
    cumulative_twr = 1.0
    cumulative_contributions = 0.0

    for dt, event_type, value in events:
        if dt >= start:
            break
        if event_type in {"external_cash", "internal_cash"}:
            cash += float(value)
            if event_type == "external_cash":
                cumulative_contributions += float(value)
        elif event_type == "buy":
            symbol, qty, price = value
            positions[symbol] = positions.get(symbol, 0.0) + qty
            last_price[symbol] = price
            cash -= qty * price
        elif event_type == "sell":
            symbol, qty, price = value
            positions[symbol] = positions.get(symbol, 0.0) - qty
            if abs(positions[symbol]) < 1e-10:
                positions.pop(symbol, None)
            last_price[symbol] = price
            cash += qty * price

    for day in index:
        external_flow = 0.0
        for event_type, value in by_day.get(day.normalize(), []):
            if event_type == "external_cash":
                flow = float(value)
                cash += flow
                external_flow += flow
                cumulative_contributions += flow
            elif event_type == "internal_cash":
                cash += float(value)
            elif event_type == "buy":
                symbol, qty, price = value
                positions[symbol] = positions.get(symbol, 0.0) + qty
                last_price[symbol] = price
                cash -= qty * price
            elif event_type == "sell":
                symbol, qty, price = value
                positions[symbol] = positions.get(symbol, 0.0) - qty
                if abs(positions[symbol]) < 1e-10:
                    positions.pop(symbol, None)
                last_price[symbol] = price
                cash += qty * price

        holdings = 0.0
        stale_symbols: list[str] = []
        for symbol, qty in positions.items():
            series = histories.get(symbol)
            price = math.nan
            if series is not None and day in series.index:
                price = _safe_float(series.loc[day], math.nan)
            if not math.isfinite(price) or price <= 0:
                price = _safe_float(last_price.get(symbol), 0.0)
                stale_symbols.append(symbol)
            else:
                last_price[symbol] = price
            holdings += qty * price

        equity = cash + holdings
        daily_return = 0.0
        if previous_equity is not None and abs(previous_equity) > 1e-9:
            daily_return = (equity - external_flow) / previous_equity - 1.0
            if math.isfinite(daily_return) and daily_return > -1.0:
                cumulative_twr *= 1.0 + daily_return
            else:
                daily_return = 0.0
        previous_equity = equity
        rows.append(
            {
                "date": day,
                "cash": cash,
                "holdings": holdings,
                "equity": equity,
                "net_contributions": cumulative_contributions,
                "daily_return": daily_return,
                "cumulative_return": cumulative_twr - 1.0,
                "stale_price_count": len(stale_symbols),
            }
        )

    return pd.DataFrame(rows)


def generate_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    """Compatibility helper: returns actual market-value curve where possible."""
    curve = compute_portfolio_equity_curve(
        trades=trades,
        deposits=pd.DataFrame(),
        withdrawals=pd.DataFrame(),
        returnsgrants=pd.DataFrame(),
        days=365,
    )
    return curve[["date", "equity"]] if not curve.empty else pd.DataFrame()


def install_analytics_hardening() -> None:
    import analytics

    analytics.compute_portfolio_xirr = compute_portfolio_xirr
    analytics.generate_equity_curve = generate_equity_curve
    analytics.compute_portfolio_equity_curve = compute_portfolio_equity_curve
