"""Fast portfolio-page adapter.

The legacy portfolio renderer is feature-rich but used to call market providers
again every time a user opened the speculation or investment page.  It also ran
stress tests and rebalancing calculations during every normal rerun.  This
adapter keeps those features, but moves both costs behind explicit user actions.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Tuple

import pandas as pd
import streamlit as st

_PATCH_LOCK = threading.RLock()
_PATCHED = False
_ORIGINAL_RISK_PANEL = None


def _number_series(
    frame: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        frame[column] = default
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


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


def _render_lazy_risk_panel(
    finance: dict,
    positions: pd.DataFrame,
    total_market: float,
) -> None:
    """Show the inexpensive risk summary first and run stress analysis on demand."""
    global _ORIGINAL_RISK_PANEL

    advanced_key = "_portfolio_advanced_risk_loaded"
    if st.session_state.get(advanced_key):
        if st.button(
            "إخفاء تحليل المخاطر المتقدم",
            icon="⚡",
            use_container_width=True,
            key="portfolio_hide_advanced_risk",
        ):
            st.session_state[advanced_key] = False
            st.rerun()
        if callable(_ORIGINAL_RISK_PANEL):
            _ORIGINAL_RISK_PANEL(finance, positions, total_market)
        return

    from components import render_kpi, safe_fmt
    from views import portfolio

    with st.expander("🛡️ ملخص مخاطر المحفظة", expanded=False):
        cash = _safe_float((finance or {}).get("cash"))
        portfolio_value = _safe_float(
            (finance or {}).get("portfolio_value"),
            cash + total_market,
        )
        cash_pct = cash / portfolio_value * 100 if portfolio_value > 0 else 0.0
        risk_score = None
        calculator = getattr(portfolio, "calculate_portfolio_risk_score", None)
        if callable(calculator) and not positions.empty:
            try:
                risk_score = _safe_float(calculator(positions, cash_pct))
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
                "غير متاح" if risk_score is None else f"{risk_score:.0f}/100",
                "neutral"
                if risk_score is None
                else "danger"
                if risk_score >= 70
                else "success",
            )

        st.caption(
            "اختبار الضغط وبوابات المخاطر واقتراحات إعادة التوازن لا تعمل "
            "تلقائيًا، لتجنب إبطاء فتح الصفحة."
        )
        if st.button(
            "تشغيل تحليل المخاطر المتقدم",
            icon="🧪",
            type="secondary",
            use_container_width=True,
            key="portfolio_load_advanced_risk",
        ):
            st.session_state[advanced_key] = True
            st.rerun()


def _install_fast_path() -> None:
    global _PATCHED, _ORIGINAL_RISK_PANEL
    if _PATCHED:
        return
    with _PATCH_LOCK:
        if _PATCHED:
            return
        from views import portfolio

        portfolio._refresh_open_positions = prepare_open_positions
        _ORIGINAL_RISK_PANEL = portfolio._render_risk_panel
        portfolio._render_risk_panel = _render_lazy_risk_panel
        _PATCHED = True


def view_portfolio(finance, key):
    _install_fast_path()
    from views.portfolio import view_portfolio as renderer

    renderer(finance, key)
