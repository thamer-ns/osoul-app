from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd
import streamlit as st

from data_normalizer import normalize_ohlcv
from database import fetch_table
from market_data import get_chart_history, get_ticker_symbol
from quality_engine import quality_label, quality_score
from views.shared import _extract_ai, _fmt_price, _generate_ai_report_flex


_ACTIONABLE = "ACTIONABLE"


def _safe_number(value: Any, default: float = 0.0) -> float:
    """Convert to a finite number; NaN/inf must never leak into signal cards."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _recommendation_kind(value: object, direction: object = None) -> str:
    """Map Arabic/English report wording without confusing blocked signals with holds."""
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction in {"buy", "bull", "bullish", "long"}:
        return "buy"
    if normalized_direction in {"sell", "bear", "bearish", "short"}:
        return "sell"

    text = str(value or "").strip().lower()
    if any(token in text for token in ("buy", "شراء", "تجميع", "صاعد", "صعود", "ارتداد")):
        return "buy"
    if any(
        token in text
        for token in ("sell", "بيع", "تقليل", "هابط", "هبوط", "خروج", "تحوط", "كسر")
    ):
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


def _decision_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Recover decision fields retained in the raw report by the shared extractor."""
    raw = extracted.get("raw")
    raw = raw if isinstance(raw, dict) else {}
    decision = raw.get("decision_engine")
    decision = decision if isinstance(decision, dict) else {}
    plan = decision.get("plan")
    if not isinstance(plan, dict):
        plan = raw.get("risk_plan") if isinstance(raw.get("risk_plan"), dict) else {}

    lifecycle = str(
        raw.get("lifecycle_status")
        or decision.get("status")
        or "UNKNOWN"
    ).strip().upper()
    direction = str(raw.get("direction") or decision.get("direction") or "neutral").strip().lower()
    opportunity = str(
        raw.get("opportunity_label")
        or decision.get("opportunity_label")
        or raw.get("opportunity_type")
        or decision.get("opportunity_type")
        or "غير مصنف"
    ).strip()
    return {
        "raw": raw,
        "decision": decision,
        "plan": plan,
        "lifecycle": lifecycle,
        "direction": direction,
        "direction_score": _safe_number(
            raw.get("direction_score", decision.get("direction_score", 0.0))
        ),
        "opportunity": opportunity,
        "plan_id": plan.get("plan_id"),
    }


def _entry_text(extracted: Dict[str, Any], plan: Dict[str, Any]) -> str:
    low = plan.get("entry_low")
    high = plan.get("entry_high")
    if low is not None and high is not None:
        return f"{_fmt_price(low)} – {_fmt_price(high)}"

    entry = extracted.get("entry") or {}
    zone = entry.get("entry_zone") if isinstance(entry, dict) else entry
    if isinstance(zone, str) and zone.strip():
        return zone.strip()
    return _fmt_price(zone)


def _render_signal_card(item: Dict[str, Any], show_details: bool) -> None:
    symbol = str(item.get("symbol") or "—")
    timeframe = str(item.get("timeframe") or "—")
    extracted = item.get("extracted") or {}
    decision = _decision_fields(extracted)
    plan = decision["plan"]
    recommendation = str(extracted.get("recommendation") or "انتظار")
    kind = _recommendation_kind(recommendation, decision["direction"])
    lifecycle = decision["lifecycle"]
    confidence = _safe_number(extracted.get("confidence"))
    direction_score = decision["direction_score"]
    entry_text = _entry_text(extracted, plan)
    risk = extracted.get("risk") or {}
    stop = plan.get("stop", risk.get("stop"))
    reward_risk = plan.get("rr", risk.get("rr"))
    target = plan.get("target1", _target_one(extracted))
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
            st.caption(
                f"التصنيف: {decision['opportunity']}"
                + (f" — رقم الخطة: {decision['plan_id']}" if decision["plan_id"] else "")
            )
        with state_col:
            if lifecycle == _ACTIONABLE and kind == "buy":
                st.success(f"قابلة للتنفيذ — {recommendation}")
            elif lifecycle == _ACTIONABLE and kind == "sell":
                st.error(f"هابطة قابلة للتنفيذ — {recommendation}")
            elif lifecycle == "BLOCKED":
                st.warning(f"محظورة — {recommendation}")
            elif lifecycle == "HEADS_UP":
                st.info(f"مراقبة — {recommendation}")
            else:
                st.info(f"لا توجد فرصة مكتملة — {recommendation}")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("ثقة الأدلة", f"{confidence:.0f}%")
        with c2:
            st.metric("درجة الاتجاه", f"{direction_score:+.1f}")
        with c3:
            st.metric("جودة البيانات", f"{quality:.1f}/100")
        with c4:
            st.metric("حالة الخطة", lifecycle)

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("منطقة الدخول", entry_text)
        with p2:
            st.metric("وقف الخسارة", _fmt_price(stop))
        with p3:
            st.metric("الهدف الأول", _fmt_price(target))
        with p4:
            rr_value = _safe_number(reward_risk)
            st.metric("العائد إلى المخاطرة", f"{rr_value:.2f}" if rr_value > 0 else "—")

        if quality < 60:
            st.warning("جودة البيانات منخفضة؛ لا تعتمد الإشارة قبل مراجعة الشارت والمصدر.")
        if lifecycle != _ACTIONABLE:
            st.info("الخطة للمراقبة فقط أو محظورة؛ لا تُعامل كإشارة دخول تنفيذية.")
        st.caption(
            "لا يُعتمد الاختراق أو الكسر أو ضرب الوقف إلا بعد إغلاق شمعة الفاصل المحدد، "
            "وتظل الخطة فعالة حتى تحقق الأهداف أو تُبطل وفق قاعدة الإغلاق أو تنتهي مدتها."
        )
        if show_details:
            with st.expander("تفاصيل التقرير المنظم"):
                st.json(decision["raw"])


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
        "قرار مركزي واحد يفرّق بين اتجاه الإشارة وثقة الأدلة وحالة التنفيذ، "
        "ويبني الدخول والوقف وثلاثة أهداف بتأكيد إغلاق الشمعة."
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
            decision = _decision_fields(extracted)
            if decision["lifecycle"] != _ACTIONABLE:
                continue
            kind = _recommendation_kind(
                extracted.get("recommendation"),
                decision["direction"],
            )
            if kind == "buy":
                st.toast(f"فرصة شراء قابلة للتنفيذ لـ {symbol}", icon="📈")
            elif kind == "sell":
                st.toast(f"إشارة هابطة قابلة للتنفيذ لـ {symbol}", icon="📉")
        st.session_state["generated_signals"] = results

    results = st.session_state.get("generated_signals") or []
    if not results:
        st.info("اختر الأسهم والفاصل ثم ولّد الإشارات.")
        return
    for item in results:
        _render_signal_card(item, show_details=show_details)
