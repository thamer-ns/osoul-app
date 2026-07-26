from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd
import streamlit as st

from data_normalizer import normalize_ohlcv
from database import fetch_table
from market_data import get_chart_history, get_ticker_symbol
from quality_engine import quality_label, quality_score
from views.shared import _extract_ai, _fmt_price, _generate_ai_report_flex


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _recommendation_kind(value: object) -> str:
    text = str(value or "").strip().lower()
    if "buy" in text or "شراء" in text:
        return "buy"
    if "sell" in text or "بيع" in text or "تقليل" in text:
        return "sell"
    return "hold"


def _symbol_universe(finance: dict) -> list[str]:
    symbols: set[str] = set()
    trades = finance.get("all_trades", pd.DataFrame()) if isinstance(finance, dict) else pd.DataFrame()
    if isinstance(trades, pd.DataFrame) and not trades.empty and "symbol" in trades.columns:
        for raw in trades["symbol"].dropna().astype(str):
            symbol = get_ticker_symbol(raw)
            if symbol:
                symbols.add(symbol)

    watchlist = fetch_table("watchlist")
    if isinstance(watchlist, pd.DataFrame) and not watchlist.empty and "symbol" in watchlist.columns:
        for raw in watchlist["symbol"].dropna().astype(str):
            symbol = get_ticker_symbol(raw)
            if symbol:
                symbols.add(symbol)
    return sorted(symbols)


def _history_quality(symbol: str, timeframe: str) -> tuple[float, str, int]:
    years = 1 if timeframe in {"15m", "1h", "4h"} else 3
    try:
        history = get_chart_history(symbol, years=years, interval=timeframe)
        history = normalize_ohlcv(history)
        if history is None or history.empty:
            return 0.0, "غير متاح", 0
        score = float(quality_score(history))
        source = str(
            (getattr(history, "attrs", {}) or {}).get("source")
            or ((getattr(history, "attrs", {}) or {}).get("data_lineage") or {}).get("source")
            or "غير معروف"
        )
        return score, source, int(len(history))
    except Exception:
        return 0.0, "غير متاح", 0


def _target_one(extracted: Dict[str, Any]):
    targets = extracted.get("targets") or []
    if not isinstance(targets, list) or not targets:
        return None
    first = targets[0]
    return first.get("price") if isinstance(first, dict) else first


def _render_signal_card(item: Dict[str, Any], show_details: bool) -> None:
    symbol = str(item.get("symbol") or "—")
    timeframe = str(item.get("timeframe") or "—")
    extracted = item.get("extracted") or {}
    recommendation = str(extracted.get("recommendation") or "انتظار")
    kind = _recommendation_kind(recommendation)
    confidence = _safe_number(extracted.get("confidence"))
    direction_score = _safe_number(
        extracted.get("direction_score"),
        0.0,
    )
    entry = (extracted.get("entry") or {}).get("entry_zone")
    risk = extracted.get("risk") or {}
    stop = risk.get("stop")
    reward_risk = risk.get("rr")
    target = _target_one(extracted)
    quality = _safe_number(item.get("quality"))

    with st.container(border=True):
        title_col, state_col = st.columns([3, 1])
        with title_col:
            st.subheader(f"{symbol} — {timeframe}")
            st.caption(
                f"المصدر: {item.get('source', 'غير معروف')} — "
                f"{int(item.get('rows', 0))} شمعة — "
                f"تم التوليد: {item.get('generated_at', '—')}"
            )
        with state_col:
            if kind == "buy":
                st.success(f"شراء — {recommendation}")
            elif kind == "sell":
                st.warning(f"بيع/تقليل — {recommendation}")
            else:
                st.info(f"انتظار — {recommendation}")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("ثقة الأدلة", f"{confidence:.0f}%")
        with c2:
            st.metric("درجة الاتجاه", f"{direction_score:+.1f}")
        with c3:
            st.metric("جودة البيانات", f"{quality:.1f}/100")
        with c4:
            st.metric("تصنيف الجودة", quality_label(quality))

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("منطقة الدخول", _fmt_price(entry))
        with p2:
            st.metric("وقف الخسارة", _fmt_price(stop))
        with p3:
            st.metric("الهدف الأول", _fmt_price(target))
        with p4:
            st.metric("العائد إلى المخاطرة", f"{_safe_number(reward_risk):.2f}")

        if quality < 60:
            st.warning("جودة البيانات منخفضة؛ لا تعتمد الإشارة قبل مراجعة الشارت والمصدر.")
        st.caption(
            "لا يُعتمد الاختراق أو الكسر إلا بعد إغلاق شمعة الفاصل المحدد، "
            "وتظل الإشارة فعالة حتى تحقق الأهداف أو يُكسر وقفها وفق خطة المخاطر."
        )
        if show_details:
            with st.expander("تفاصيل التقرير الخام"):
                st.json(extracted.get("raw") or {})


def _generate_signal(symbol: str, timeframe: str) -> Dict[str, Any]:
    report = _generate_ai_report_flex(symbol, timeframe)
    extracted = _extract_ai(report)
    quality, source, rows = _history_quality(symbol, timeframe)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "extracted": extracted,
        "quality": quality,
        "source": source,
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def view_signals(fin: dict):
    st.header("🚦 الإشارات الفنية")
    st.caption(
        "إشارات صعود وهبوط بخطة دخول ومخاطر، مع فصل اتجاه الإشارة عن ثقة الأدلة."
    )
    symbols = _symbol_universe(fin or {})
    if not symbols:
        st.info("لا توجد رموز في المحفظة أو قائمة المراقبة.")
        return

    left, middle, right = st.columns([2, 1, 1])
    with left:
        selected = st.multiselect(
            "الأسهم",
            symbols,
            default=symbols[: min(5, len(symbols))],
        )
    with middle:
        timeframe = st.selectbox(
            "الفاصل",
            ["15m", "1h", "4h", "1d", "1wk"],
            index=3,
        )
    with right:
        show_details = st.toggle("إظهار التفاصيل", value=False)

    if st.button(
        "توليد الإشارات",
        type="primary",
        use_container_width=True,
        disabled=not selected,
    ):
        results = []
        for symbol in selected:
            with st.spinner(f"تحليل {symbol} على {timeframe}..."):
                item = _generate_signal(symbol, timeframe)
            extracted = item.get("extracted") or {}
            if not extracted.get("ok"):
                st.error(f"{symbol}: تعذر توليد تقرير صالح")
                continue
            results.append(item)
            kind = _recommendation_kind(extracted.get("recommendation"))
            if kind == "buy":
                st.toast(f"إشارة شراء جديدة لـ {symbol}", icon="📈")
            elif kind == "sell":
                st.toast(f"إشارة بيع أو تقليل لـ {symbol}", icon="📉")
        st.session_state["generated_signals"] = results

    results = st.session_state.get("generated_signals") or []
    if not results:
        st.info("اختر الأسهم والفاصل ثم ولّد الإشارات.")
        return
    for item in results:
        _render_signal_card(item, show_details=show_details)
