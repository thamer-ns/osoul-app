"""Fast portfolio-page adapter.

The legacy portfolio renderer is feature-rich but used to call market providers
again every time a user opened the speculation or investment page.  The router
already supplies a calculated tenant snapshot, so this adapter permanently
replaces that duplicate network refresh with a local preparation step.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Tuple

import pandas as pd

_PATCH_LOCK = threading.RLock()
_PATCHED = False


def _number_series(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        frame[column] = default
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def prepare_open_positions(
    positions: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Recalculate display columns from the cached stored-price snapshot only."""
    if positions is None or positions.empty:
        return (
            pd.DataFrame() if positions is None else positions.copy(),
            {},
        )

    from views.shared import _normalize_symbol

    frame = positions.copy()
    frame["quantity"] = _number_series(frame, "quantity")
    frame["entry_price"] = _number_series(frame, "entry_price")
    frame["current_price"] = _number_series(frame, "current_price")
    frame["prev_close"] = _number_series(frame, "prev_close")

    if "symbol" not in frame.columns:
        frame["symbol"] = ""
    frame["symbol"] = frame["symbol"].astype(str).map(_normalize_symbol)

    missing_price = frame["current_price"].le(0)
    frame.loc[missing_price, "current_price"] = frame.loc[
        missing_price,
        "entry_price",
    ]
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

    if "price_source" not in frame.columns:
        frame["price_source"] = "stored"
    else:
        source = frame["price_source"].astype(str).str.strip()
        frame["price_source"] = source.where(source.ne(""), "stored")
    if "price_stale" not in frame.columns:
        frame["price_stale"] = True
    else:
        frame["price_stale"] = frame["price_stale"].fillna(True).astype(bool)
    if "price_fetched_at" not in frame.columns:
        frame["price_fetched_at"] = "—"
    frame["status_ar"] = "مفتوحة"
    return frame, {}


def _install_fast_path() -> None:
    global _PATCHED
    if _PATCHED:
        return
    with _PATCH_LOCK:
        if _PATCHED:
            return
        from views import portfolio

        portfolio._refresh_open_positions = prepare_open_positions
        _PATCHED = True


def view_portfolio(finance, key):
    _install_fast_path()
    from views.portfolio import view_portfolio as renderer

    renderer(finance, key)
