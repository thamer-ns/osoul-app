"""Technical-analysis UI using the current SC-V92.5 closed-candle contract."""
from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd
import streamlit as st

from ai_engine_core.sc_feature_pack_v925 import build_sc_feature_pack
from candle_confirmation import completed_candles
from components import render_custom_table
from market_data import get_chart_history
from technical_indicators import compute_advanced_technical_pack

logger = logging.getLogger("osoli.analysis.technical")


def _sf(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _direction_ar(value: Any) -> str:
    text = str(value or "").strip().lower()
    if value == 1 or text in {"bullish", "buy", "long", "صاعد"}:
        return "صاعد"
    if value == -1 or text in {"bearish", "sell", "short", "هابط"}:
        return "هابط"
    return "محايد"


def period_for_interval(interval: str) -> str:
    """Return enough history for the requested timeframe and provider fallback."""
    value = str(interval or "1d").strip().lower()
    return {
        "1m": "7d",
        "2m": "60d",
        "5m": "60d",
        "15m": "60d",
        "30m": "60d",
        "60m": "2y",
        "1h": "2y",
        "4h": "5y",
        "1d": "5y",
        "1wk": "15y",
        "1w": "15y",
        "1mo": "max",
    }.get(value, "5y")


@st.cache_data(ttl=180, max_entries=128, show_spinner=False)
def _history_cached(symbol: str, interval: str, period: str) -> pd.DataFrame:
    frame = get_chart_history(symbol, period=period, interval=interval)
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


@st.cache_data(ttl=300, max_entries=128, show_spinner=False)
def _advanced_pack_cached(symbol: str, interval: str, period: str) -> dict:
    frame = completed_candles(
        _history_cached(symbol, interval, period),
        interval=interval,
    )
    if frame.empty:
        return {}
    return compute_advanced_technical_pack(
        frame,
        symbol=symbol,
        timeframe=interval,
    )


@st.cache_data(ttl=180, max_entries=128, show_spinner=False)
def _sc_pack_cached(symbol: str, interval: str, period: str) -> dict:
    frame = completed_candles(
        _history_cached(symbol, interval, period),
        interval=interval,
    )
    if frame.empty:
        return {}
    normalized = str(symbol or "").upper()
    market = "SAUDI" if normalized.endswith(".SR") or normalized.isdigit() else ""
    asset_class = "stock"
    return build_sc_feature_pack(
        frame,
        interval=interval,
        asset_class=asset_class,
        market=market,
    )


def _quality(df: pd.DataFrame, interval: str) -> Dict[str, Any]:
    issues: list[str] = []
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {"ok": False, "score": 0, "issues": ["لا توجد شموع"], "rows": 0}
    required = {"Open", "High", "Low", "Close"}
    missing = sorted(required - set(df.columns))
    if missing:
        issues.append("أعمدة ناقصة: " + ", ".join(missing))
    if {"High", "Low"}.issubset(df.columns):
        high = pd.to_numeric(df["High"], errors="coerce")
        low = pd.to_numeric(df["Low"], errors="coerce")
        bad = int((high < low).sum())
        if bad:
            issues.append(f"{bad} شموع فيها أعلى أقل من أدنى")
    normalized = str(interval or "1d").lower()
    minimum = (
        60
        if normalized == "1mo"
        else 156
        if normalized in {"1wk", "1w"}
        else 200
        if normalized == "1d"
        else 120
    )
    if len(df) < minimum:
        issues.append(f"عدد الشموع أقل من الحد المفضل ({minimum})")
    available = [column for column in required if column in df.columns]
    null_ratio = float(df[available].isna().mean().mean()) if available else 1.0
    if null_ratio > 0.01:
        issues.append(f"نسبة قيم ناقصة {null_ratio * 100:.1f}%")
    attrs = getattr(df, "attrs", {}) or {}
    lineage = (
        attrs.get("data_lineage")
        if isinstance(attrs.get("data_lineage"), dict)
        else {}
    )
    provider_score = lineage.get("quality_score")
    score = max(0, 100 - len(issues) * 15 - int(null_ratio * 100))
    if isinstance(provider_score, (int, float)):
        score = min(score, int(provider_score))
    return {
        "ok": not issues,
        "score": score,
        "issues": issues,
        "rows": int(len(df)),
        "last": str(df.index[-1]),
    }


def _source_info(df: pd.DataFrame) -> tuple[str, str, dict[str, Any]]:
    attrs = getattr(df, "attrs", {}) or {}
    lineage = (
        attrs.get("data_lineage")
        if isinstance(attrs.get("data_lineage"), dict)
        else {}
    )
    source = str(lineage.get("source") or attrs.get("source") or "غير معروف")
    fetched_at = str(lineage.get("fetched_at") or "—")
    return source, fetched_at, lineage


def _render_provider_lineage(lineage: dict[str, Any]) -> None:
    attempts = list(lineage.get("provider_attempts") or [])
    with st.expander("مصادر البيانات ومحاولات الجلب", expanded=False):
        if not attempts:
            st.caption("لا توجد تفاصيل محاولات من طبقة الدمج الحالية.")
            return
        rows = [
            {
                "المزود": item.get("provider"),
                "النتيجة": "نجح" if item.get("ok") else "لم يُستخدم",
                "الرمز المحلول": item.get("resolved_symbol") or "—",
                "الشموع": item.get("rows") or 0,
                "الجودة": item.get("quality_score"),
                "الزمن ms": item.get("elapsed_ms"),
                "السبب": item.get("reason") or "—",
            }
            for item in attempts
        ]
        render_custom_table(pd.DataFrame(rows))
        st.caption(
            "يُستخدم أول مزود يجتاز فحص OHLCV؛ المصادر المؤجلة تبقى حلًا أخيرًا."
        )


def _render_signal_table(signals: list[dict]) -> None:
    if not signals:
        st.caption("لا توجد إشارة تنفيذية جديدة على آخر إغلاق.")
        return
    frame = pd.DataFrame(signals)
    labels = {
        "type": "النوع",
        "kind": "الإشارة",
        "code": "الحدث",
        "direction": "الاتجاه",
        "price": "السعر",
        "level": "المستوى",
        "source": "المرجع",
        "trigger": "التأكيد",
        "reason": "السبب",
        "confirmed_on_close": "مؤكد بالإغلاق",
    }
    config = []
    for column in frame.columns:
        kind = (
            "money"
            if column in {"price", "level"}
            else "bool"
            if column == "confirmed_on_close"
            else "text"
        )
        config.append((column, labels.get(column, column), kind))
    render_custom_table(frame, config)


def _render_indicator(title: str, result: Dict[str, Any]) -> None:
    with st.expander(title, expanded=False):
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            st.metric("الاتجاه", _direction_ar(result.get("bias")))
        with c2:
            st.metric("الثقة", f"{_sf(result.get('confidence')):.0f}%")
        with c3:
            st.info(str(result.get("summary") or "لا يوجد ملخص"))
        st.caption(
            f"درجة الاتجاه: {_sf(result.get('direction_score')):+.1f}/100 — "
            "التأكيد: إغلاق الشمعة"
        )
        for item in result.get("evidence") or []:
            st.write(f"- {item}")
        _render_signal_table(result.get("signals") or [])
        features = result.get("features") or {}
        if features:
            rows = pd.DataFrame(
                [
                    {"البند": key, "القيمة": value}
                    for key, value in features.items()
                ]
            )
            render_custom_table(
                rows,
                [("البند", "البند", "text"), ("القيمة", "القيمة", "auto")],
            )
        errors = (result.get("errors") or []) + (result.get("warnings") or [])
        if errors:
            st.warning(" — ".join(str(item) for item in errors))


def _save_pack_once(
    pack: dict,
    symbol: str,
    interval: str,
    df: pd.DataFrame,
) -> None:
    if not pack or df.empty:
        return
    latest = str(df.index[-1])
    key = f"advanced_saved:{symbol}:{interval}:{latest}"
    if st.session_state.get(key):
        return
    try:
        from ai_engine_core.db import save_advanced_indicators

        if save_advanced_indicators(
            symbol=symbol,
            timeframe=interval,
            indicators=pack,
        ):
            st.session_state[key] = True
    except Exception:
        logger.debug("advanced indicator persistence skipped", exc_info=True)


def _render_advanced(
    df: pd.DataFrame,
    symbol: str,
    interval: str,
    period: str,
) -> None:
    if df.empty:
        st.warning("لا توجد بيانات كافية لحساب المؤشرات المتقدمة")
        return
    closed = completed_candles(df, interval=interval)
    with st.spinner("حساب المؤشرات المتقدمة..."):
        pack = _advanced_pack_cached(symbol, interval, period)
    if not pack:
        st.warning("تعذر حساب حزمة المؤشرات المتقدمة.")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("الاتجاه العام", _direction_ar(pack.get("bias")))
    with c2:
        st.metric("درجة الاتجاه", f"{_sf(pack.get('direction_score')):+.1f}")
    with c3:
        st.metric("ثقة الأدلة", f"{_sf(pack.get('confidence')):.0f}%")
    with c4:
        st.metric(
            "اتفاق المؤشرات",
            f"{_sf((pack.get('features') or {}).get('agreement')) * 100:.0f}%",
        )
    st.info(str(pack.get("summary") or "النتيجة غير متاحة"))
    st.caption(
        "المؤشرات المساندة لا تنشئ خطة وحدها؛ عقد SC والبنية والوقف "
        "والأهداف هي بوابة التنفيذ."
    )
    _render_signal_table(pack.get("signals") or [])
    _render_indicator("1) RLS المتكيف", pack.get("rls_forecast") or {})
    _render_indicator("2) RSI الموزون بالتقلب", pack.get("chaos_wrsi") or {})
    _render_indicator(
        "3) شرائح الحجم السعري",
        pack.get("volume_profile_clusters") or {},
    )
    _render_indicator(
        "4) اختراق وكسر خطوط الاتجاه",
        pack.get("trendline_breakout") or {},
    )
    _save_pack_once(pack, symbol, interval, closed)


def _render_sc_contract(symbol: str, interval: str, period: str) -> None:
    with st.spinner("تحليل عقد SC‑V92.5 من الشموع المكتملة..."):
        pack = _sc_pack_cached(symbol, interval, period)
    if not pack or not pack.get("ok"):
        st.warning("تعذر بناء عقد SC‑V92.5 على هذا الفاصل.")
        if pack.get("reason"):
            st.caption(
                f"السبب: {pack.get('reason')} — المتوفر: {pack.get('have', '—')} "
                f"— المطلوب: {pack.get('need', '—')}"
            )
        return

    plan = pack.get("risk_plan") if isinstance(pack.get("risk_plan"), dict) else {}
    veto = (
        pack.get("opposition_veto")
        if isinstance(pack.get("opposition_veto"), dict)
        else {}
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("اتجاه SC", _direction_ar(pack.get("direction")))
    c2.metric("الثقة", f"{int(pack.get('confidence') or 0)}%")
    c3.metric("الحدث", str(pack.get("event_code") or "NONE"))
    c4.metric("الخطة", "صالحة" if plan.get("valid") else "مراقبة")

    st.caption(
        "الأولوية: كلاستر الدعم/المقاومة ← Pivot مؤكد ← الأدوات الثانوية. "
        "كل الكسر والوقف وتحوّل الدور يعتمد إغلاق الشمعة."
    )
    if veto.get("blocked"):
        st.warning(str(veto.get("reason") or "كلاستر مقابل يمنع الخطة"))
    elif pack.get("qualified"):
        st.success("اكتمل توافق عقد SC وهندسة المخاطرة على آخر إغلاق.")
    else:
        st.info("القراءة تحت المراقبة ولم تتحول إلى خطة تنفيذ مكتملة.")

    sr = pack.get("sr") if isinstance(pack.get("sr"), dict) else {}
    sr_rows = []
    for label, value in (
        ("الدعم", sr.get("support")),
        ("المقاومة", sr.get("resistance")),
    ):
        row = value if isinstance(value, dict) else {}
        sr_rows.append(
            {
                "النوع": label,
                "المستوى": row.get("level"),
                "الحد الأدنى": row.get("low"),
                "الحد الأعلى": row.get("high"),
                "اللمسات": row.get("touches"),
                "العمر بالشموع": row.get("age_bars"),
            }
        )
    render_custom_table(pd.DataFrame(sr_rows))

    event_rows = list(pack.get("event_candidates") or [])
    if event_rows:
        st.markdown("**الأحداث المرشحة المرتبة**")
        _render_signal_table(event_rows)

    if plan.get("valid"):
        targets = list(plan.get("targets") or [])
        plan_rows = [
            {"البند": "الدخول", "القيمة": plan.get("entry"), "المصدر": "إغلاق الزناد"},
            {"البند": "الوقف", "القيمة": plan.get("stop"), "المصدر": plan.get("stop_source")},
        ]
        sources = list(plan.get("target_sources") or [])
        for index, target in enumerate(targets, start=1):
            plan_rows.append(
                {
                    "البند": f"T{index}",
                    "القيمة": target,
                    "المصدر": sources[index - 1] if index <= len(sources) else "—",
                }
            )
        render_custom_table(pd.DataFrame(plan_rows))
        st.caption(
            f"المخاطرة: {_sf(plan.get('risk_atr')):.2f} ATR — "
            f"العائد الأول: {_sf(plan.get('first_rr')):.2f}R — "
            "بعد T1 يستخدم ATR(22) × 3 ولا يوسّع الوقف."
        )

    for reason in pack.get("reasons") or []:
        st.write(f"- {reason}")
    if pack.get("warnings"):
        st.warning(" — ".join(str(item) for item in pack["warnings"]))


def _render_chart(
    symbol: str,
    interval: str,
    period: str,
    df: pd.DataFrame,
) -> None:
    try:
        from charts import render_technical_chart

        render_technical_chart(symbol, period=period, interval=interval)
    except Exception:
        logger.exception("technical chart failed")
        if not df.empty:
            st.dataframe(df.tail(30), use_container_width=True)
        else:
            st.warning("تعذر عرض الشارت")
    st.caption(
        "الاختراق أو الكسر لا يُعتمد إلا بعد إغلاق الشمعة على الفاصل المحدد."
    )


def view_technical(symbol: str, interval: str = "1d"):
    st.subheader("📈 التحليل الفني")
    period = period_for_interval(interval)
    try:
        df = _history_cached(symbol, interval, period)
    except Exception:
        logger.exception("history loading failed")
        df = pd.DataFrame()

    quality = _quality(df, interval)
    source, fetched_at, lineage = (
        _source_info(df) if not df.empty else ("غير متاح", "—", {})
    )
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        st.metric("جودة البيانات", f"{quality['score']}/100")
    with q2:
        st.metric("عدد الشموع", quality.get("rows", 0))
    with q3:
        st.metric("المصدر", source)
    with q4:
        st.metric("الفاصل", interval)
    closed = (
        completed_candles(df, interval=interval)
        if not df.empty
        else pd.DataFrame()
    )
    last_closed = str(closed.index[-1]) if not closed.empty else "—"
    excluded = int(
        (getattr(closed, "attrs", {}) or {})
        .get("candle_confirmation", {})
        .get("excluded_incomplete_bars", 0)
        or 0
    )
    st.caption(
        f"آخر شمعة معروضة: {quality.get('last', '—')} — "
        f"آخر إغلاق معتمد: {last_closed} — وقت الجلب: {fetched_at}"
    )
    if excluded:
        st.info(
            "الشمعة الحية ظاهرة في الرسم فقط، ومستبعدة من المؤشرات والقرار "
            "حتى الإغلاق."
        )
    if quality.get("issues"):
        with st.expander("ملاحظات جودة البيانات"):
            for issue in quality["issues"]:
                st.write(f"- {issue}")
    _render_provider_lineage(lineage)

    mode = st.radio(
        "طريقة العرض",
        ["الرسم الفني", "عقد SC‑V92.5", "المؤشرات المتقدمة"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"technical_mode:{symbol}:{interval}",
    )
    if mode == "الرسم الفني":
        _render_chart(symbol, interval, period, df)
    elif mode == "عقد SC‑V92.5":
        _render_sc_contract(symbol, interval, period)
    else:
        _render_advanced(df, symbol, interval, period)


def render_technical_tab(symbol: str, interval: str = "1d"):
    return view_technical(symbol, interval=interval)
