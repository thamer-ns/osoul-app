from __future__ import annotations

import pandas as pd
import streamlit as st

from components import render_ticker_card
from database import fetch_table
from market_data import fetch_batch_data
from views.shared import (
    _clean_symbols_list,
    _normalize_symbol,
    _safe_status_series,
)


def view_pulse() -> None:
    """Show a live market snapshot for open stock positions only."""
    st.header("📡 نبض المحفظة")
    st.caption(
        "متابعة سريعة لأسعار أسهمك المفتوحة وتغيرها اليومي دون الدخول إلى "
        "كل محفظة على حدة. هذه شاشة متابعة سوقية وليست توصية شراء أو بيع."
    )

    trades = fetch_table("trades")
    if not isinstance(trades, pd.DataFrame) or trades.empty:
        st.info("لا توجد صفقات مسجلة لعرض نبضها")
        return

    status = _safe_status_series(trades)
    open_positions = (
        trades[status == "open"].copy()
        if len(status)
        else pd.DataFrame()
    )
    if open_positions.empty:
        st.info("لا توجد مراكز مفتوحة حاليًا")
        return

    if "asset_type" in open_positions.columns:
        asset_type = open_positions["asset_type"].astype(str).str.strip().str.lower()
        open_positions = open_positions[~asset_type.eq("sukuk")].copy()
    if open_positions.empty:
        st.info("لا توجد أسهم مفتوحة؛ الصكوك تُتابع من قسم المحافظ")
        return

    symbols = (
        _clean_symbols_list(
            open_positions["symbol"].dropna().astype(str).unique().tolist()
        )
        if "symbol" in open_positions.columns
        else []
    )
    if not symbols:
        st.info("لا توجد رموز أسهم صالحة للعرض")
        return

    with st.spinner("جاري قراءة نبض المراكز المفتوحة..."):
        data = fetch_batch_data(symbols)
    if not data:
        st.warning("تعذر جلب أسعار النبض الآن؛ جرّب مرة أخرى لاحقًا")
        return

    st.caption(f"عدد الأسهم المفتوحة المتابعة: {len(symbols)}")
    columns = st.columns(4)
    shown: set[str] = set()
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

    st.info(
        "فائدة النبض: اكتشاف السهم الأكثر صعودًا أو هبوطًا اليوم بسرعة، "
        "ثم الانتقال إلى المحفظة أو مركز التحليل لدراسة السبب واتخاذ القرار."
    )
